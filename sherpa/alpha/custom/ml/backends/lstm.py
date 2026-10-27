"""LSTM 后端（torch）：每行看同一个 symbol 最近 `seq_len` 根 bar 的特征序列（`ModelInputs.sequences`）。

网络结构、输入预处理、checkpoint 读写都在这个文件里，**训练和推断共用这一份**——网络怎么搭、输入怎么标准化如果两边
各写一份，线上和回测会悄悄对不上（同 features.py 的原则）。训练循环在 `research/ml_training/trainers/lstm.py`。
模型文件是自描述的 checkpoint：网络超参、权重、`seq_len`、标准化用的均值 / 标准差都在里面，推断不需要别的配置。

本模块在模块级 import torch，只有 `get_backend("lstm")` 才会 import 它，没装 torch 不影响其它后端。

输入预处理（`prepare`）：
1. 每个特征减去训练窗口上的均值、除以标准差（均值 / 标准差在训练时用训练行算好，存进 checkpoint；只用过去的数据，
   不是全样本统计量）。A 组本来是 [-0.5, 0.5] 的截面排名，C 组是比例 / 分位数 / 收益，量级不同，网络需要对齐尺度；
2. 缺失（不在流动性范围内的 A 组特征、还没上线的步）填 0，也就是"跟训练窗口的均值一样"；
3. 末尾追加一个通道 `present`：这一步这个 symbol 有没有特征行，让网络能区分"真的等于均值"和"没有数据"。

设备（2026-10-26 起默认 GPU）：训练用哪个设备由 `backend_params["device"]` 决定（默认 `"cuda"`，显式写 `"cpu"` 才用 CPU），
记进 checkpoint 的 `train_device`。推断默认用训练时的设备；模型是 GPU 训练的、当前机器没有可用 GPU 时退回 CPU 并警告
（推断时两种设备的数值差异极小，可以退；训练时不退，见 `research/ml_training/trainers/lstm.py`）。环境变量 `SHERPA_TORCH_DEVICE`
可以强制指定推断设备。GPU 上打开 torch 的确定性模式（`enable_determinism`），同一个模型、同一份输入每次推断逐位相同。
"""

from __future__ import annotations

import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import torch
from torch import nn

from .base import Backend, ModelInputs

CHECKPOINT_FORMAT = "sherpa.lstm.v1"
DEVICES = ("cuda", "cpu")
INFER_DEVICE_ENV = "SHERPA_TORCH_DEVICE"


def enable_determinism() -> None:
    """GPU 上逐位可复现：cuBLAS 用固定的工作区、cuDNN 只用确定性算法、torch 遇到没有确定性实现的算子直接报错。
    `CUBLAS_WORKSPACE_CONFIG` 必须在第一次 cuBLAS 调用之前设好（之后再设不生效），所以训练和推断加载模型前都先调这里。"""
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.use_deterministic_algorithms(True)


def resolve_device(device: str) -> torch.device:
    """训练用：`cuda` 必须真的可用，不悄悄退回 CPU——两种设备训练出来的模型数值不同，悄悄换会让结果说不清是哪个设备的。"""
    if device not in DEVICES:
        raise ValueError(f"device 只能是 {DEVICES}，收到 {device!r}")
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError(
            "要求用 GPU（device='cuda'，LSTM 的默认值）训练，但 torch 看不到可用的 CUDA 设备："
            f"torch {torch.__version__}，torch.version.cuda = {torch.version.cuda}。装 CUDA 版 torch，"
            "或者在模型的 backend_params 里显式写 device='cpu'"
        )
    if device == "cuda":
        enable_determinism()
    return torch.device(device)


def inference_device(train_device: str) -> torch.device:
    forced = os.environ.get(INFER_DEVICE_ENV)
    if forced:
        return resolve_device(forced)
    if train_device == "cuda" and not torch.cuda.is_available():
        warnings.warn("模型是 GPU 训练的，当前机器没有可用的 CUDA 设备，推断退回 CPU（数值跟 GPU 推断有极小差异）", RuntimeWarning)
        return torch.device("cpu")
    return resolve_device(train_device)


class LSTMScorer(nn.Module):
    """`(B, L, K+1)` -> `(B,)`：LSTM 读完整个序列，最后一步的隐状态经一层线性输出打分。"""

    def __init__(self, input_size: int, hidden_size: int, num_layers: int, dropout: float):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size, hidden_size, num_layers=num_layers, batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        self.head = nn.Linear(hidden_size, 1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out, _ = self.lstm(x)
        return self.head(out[:, -1, :]).squeeze(-1)


@dataclass
class LSTMModel:
    """一个训练好的 LSTM：网络 + 它的输入预处理参数。"""

    net: LSTMScorer
    seq_len: int
    mean: np.ndarray  # (K,) float32
    std: np.ndarray  # (K,) float32
    hparams: dict[str, Any]
    train_device: str = "cpu"  # 训练用的设备（2026-10-26 以前的 checkpoint 没记，都是 CPU）

    @property
    def device(self) -> torch.device:
        return next(self.net.parameters()).device


def build_net(n_features: int, hparams: Mapping[str, Any]) -> LSTMScorer:
    return LSTMScorer(
        input_size=n_features + 1,
        hidden_size=int(hparams["hidden_size"]),
        num_layers=int(hparams["num_layers"]),
        dropout=float(hparams["dropout"]),
    )


def feature_stats(matrix: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """训练行上每个特征的均值 / 标准差（跳过 NaN；标准差为 0 或整列缺失时取 1，避免除零）。"""
    with warnings.catch_warnings():  # 整列缺失的特征（比如面板没取 OI）会报 "Mean of empty slice"，下面统一处理
        warnings.simplefilter("ignore", RuntimeWarning)
        mean = np.nanmean(matrix, axis=0)
        std = np.nanstd(matrix, axis=0)
    mean = np.where(np.isfinite(mean), mean, 0.0).astype("float32")
    std = np.where(np.isfinite(std) & (std > 1e-8), std, 1.0).astype("float32")
    return mean, std


def prepare(x: np.ndarray, present: np.ndarray, mean: np.ndarray, std: np.ndarray) -> torch.Tensor:
    """`ModelInputs.sequences` 的输出 -> 网络输入 `(B, L, K+1)`（见模块说明），CPU 上的张量，调用方再搬到设备上。"""
    z = (x - mean) / std
    z = np.where(np.isfinite(z), z, 0.0).astype("float32")
    return torch.from_numpy(np.concatenate([z, present[..., None].astype("float32")], axis=-1))


def predict_sequences(model: LSTMModel, x: np.ndarray, present: np.ndarray) -> np.ndarray:
    model.net.eval()
    with torch.no_grad():
        return model.net(prepare(x, present, model.mean, model.std).to(model.device)).double().cpu().numpy()


def save_checkpoint(path: Path, model: LSTMModel) -> None:
    torch.save({
        "format": CHECKPOINT_FORMAT,
        "seq_len": model.seq_len,
        "n_features": len(model.mean),
        "mean": model.mean,
        "std": model.std,
        "hparams": dict(model.hparams),
        "train_device": model.train_device,
        "state_dict": {k: v.cpu() for k, v in model.net.state_dict().items()},  # 存 CPU 张量，哪种设备都能读
    }, str(path))


def load_checkpoint(path: Path) -> LSTMModel:
    raw = torch.load(str(path), map_location="cpu", weights_only=False)
    if raw.get("format") != CHECKPOINT_FORMAT:
        raise ValueError(f"{path} 不是 {CHECKPOINT_FORMAT} 格式的模型文件（format={raw.get('format')!r}）")
    train_device = str(raw.get("train_device", "cpu"))
    device = inference_device(train_device)
    net = build_net(int(raw["n_features"]), raw["hparams"])
    net.load_state_dict(raw["state_dict"])
    net.to(device).eval()
    return LSTMModel(net, int(raw["seq_len"]), np.asarray(raw["mean"]), np.asarray(raw["std"]), dict(raw["hparams"]),
                     train_device)


class LSTMBackend(Backend):
    name = "lstm"
    suffix = ".pt"
    batch_rows = 65536

    def load(self, path: Path) -> LSTMModel:
        return load_checkpoint(path)

    def predict(self, model: LSTMModel, inputs: ModelInputs, rows: np.ndarray) -> np.ndarray:
        rows = np.asarray(rows, dtype=np.int64)
        out = np.empty(len(rows))
        for lo in range(0, len(rows), self.batch_rows):
            part = rows[lo:lo + self.batch_rows]
            x, present = inputs.sequences(part, model.seq_len)
            out[lo:lo + len(part)] = predict_sequences(model, x, present)
        return out

    def min_lookback_extra(self, params: Mapping[str, Any]) -> int:
        return int(params["seq_len"]) - 1
