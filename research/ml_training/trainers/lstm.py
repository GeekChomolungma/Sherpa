"""LSTM 后端的单个重训时点训练（torch）。跟 `lgb.py` / `xgb.py` 的树模型同一个两步流程、同一个损失定义：

- **损失**：一个 batch 放 `periods_per_batch` 期（根 bar）的全部训练行，每期算一次加权 Pearson IC（权重 = 首尾加权，
  跟 `objective.ICIRObjective` 同一个定义），损失 = 这几期 IC 的 −mean / std（只有一期时退化成 −IC）。torch 自动求导，
  不需要像树模型那样手写梯度；
- **两步训练**：① 拟合段上训练，每个 epoch 结束在内部验证段上算 IC_IR（`ICIRObjective.ic_ir`，跟树模型的早停指标同一个函数），
  连续 `patience` 个 epoch 没刷新就停，得到最佳 epoch 数；② 用整个训练窗口、同一个种子从头训练这么多个 epoch，保存这一步的模型；
- **输入**：每个训练行取同一个币最近 `seq_len` 根 bar 的特征序列（`ModelInputs.sequences`），标准化用训练行上的均值 / 标准差
  （①用拟合段的，②用整个窗口的），存进 checkpoint，推断用同一份（`sherpa/alpha/custom/ml/backends/lstm.py`）。

可复现：每个种子的两步都从 `torch.manual_seed(seed)` 和同种子的 numpy 随机数（打乱期的顺序）开始，结果只取决于数据和种子，
跟前面先训了哪个种子无关（跟 `config.LGB_PARAMS["data_random_seed"]` 要守的是同一条规矩）。
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np
import torch

from sherpa.alpha.custom.ml.backends.lstm import LSTMModel, build_net, feature_stats, predict_sequences, prepare, save_checkpoint

from dataset import TrainingFrame
from objective import ICIRObjective, period_starts
from trainers.common import FoldResult

EPS = 1e-12
PREDICT_BATCH_ROWS = 8192
NET_HPARAMS = ("hidden_size", "num_layers", "dropout")


def ic_ir_loss(pred: torch.Tensor, y: torch.Tensor, w: torch.Tensor, group: torch.Tensor, n_groups: int) -> torch.Tensor:
    """一个 batch 的 −IC_IR：`group` 是每行属于第几期（0 … n_groups−1），每期内权重归一后算加权 Pearson 相关。"""
    def per_group(values: torch.Tensor) -> torch.Tensor:
        return torch.zeros(n_groups, dtype=values.dtype).index_add(0, group, values)

    wn = w / per_group(w)[group]
    dp = pred - per_group(wn * pred)[group]
    dy = y - per_group(wn * y)[group]
    ic = per_group(wn * dp * dy) / torch.sqrt(per_group(wn * dp**2) * per_group(wn * dy**2) + EPS)
    if n_groups < 2:
        return -ic.mean()
    return -ic.mean() / (ic.std(unbiased=False) + 1e-6)


class _Periods:
    """训练集一段行（`rows`）里可以参与损失的期：每期一段连续的行（训练集按时间排好序）。"""

    def __init__(self, frame: TrainingFrame, rows: slice, min_period_rows: int):
        starts = period_starts(frame.times[rows].asi8)
        sizes = np.diff(np.append(starts, rows.stop - rows.start))
        valid = ICIRObjective(frame.y[rows], frame.weights[rows], starts, min_period_rows=min_period_rows).valid
        self.starts = (starts + rows.start)[valid]
        self.sizes = sizes[valid]

    def __len__(self) -> int:
        return len(self.starts)

    def batch(self, which: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """选中的几期 -> (训练集行号, 每行属于 batch 内第几期)。"""
        rows = np.concatenate([np.arange(s, s + n) for s, n in zip(self.starts[which], self.sizes[which])])
        group = np.repeat(np.arange(len(which)), self.sizes[which])
        return rows, group


def _predict_rows(model: LSTMModel, frame: TrainingFrame, rows: slice) -> np.ndarray:
    source = frame.source_rows[rows]
    out = np.empty(len(source))
    for lo in range(0, len(source), PREDICT_BATCH_ROWS):
        part = source[lo:lo + PREDICT_BATCH_ROWS]
        x, present = frame.inputs.sequences(part, model.seq_len)
        out[lo:lo + len(part)] = predict_sequences(model, x, present)
    return out


def _train_net(
    frame: TrainingFrame,
    rows: slice,
    params: dict[str, Any],
    *,
    seed: int,
    epochs: int,
    min_period_rows: int,
    evaluate: Optional[Callable[[LSTMModel], float]] = None,
    patience: Optional[int] = None,
) -> tuple[LSTMModel, list[float]]:
    """从种子 `seed` 开始在 `rows` 上训练至多 `epochs` 个 epoch。给了 `evaluate` 就每个 epoch 后评估、按 `patience` 早停，
    返回最好那个 epoch 的模型；否则训满 `epochs` 个，返回最后的模型。第二个返回值是各 epoch 的评估分数。"""
    torch.manual_seed(seed)
    rng = np.random.default_rng(seed)
    seq_len = int(params["seq_len"])
    mean, std = feature_stats(frame.features[rows])
    net = build_net(frame.features.shape[1], params)
    model = LSTMModel(net, seq_len, mean, std, {k: params[k] for k in NET_HPARAMS})
    optimizer = torch.optim.Adam(net.parameters(), lr=float(params["learning_rate"]), weight_decay=float(params["weight_decay"]))
    periods = _Periods(frame, rows, min_period_rows)
    if len(periods) == 0:
        raise ValueError("训练窗口里没有一期满足条件（行数足够且标签不恒定）")
    per_batch = int(params["periods_per_batch"])

    scores: list[float] = []
    best_score, best_state = -np.inf, None
    for epoch in range(epochs):
        net.train()
        order = rng.permutation(len(periods))
        for lo in range(0, len(order), per_batch):
            batch_rows, group = periods.batch(order[lo:lo + per_batch])
            x, present = frame.inputs.sequences(frame.source_rows[batch_rows], seq_len)
            pred = net(prepare(x, present, mean, std))
            loss = ic_ir_loss(
                pred,
                torch.from_numpy(frame.y[batch_rows].astype("float32")),
                torch.from_numpy(frame.weights[batch_rows].astype("float32")),
                torch.from_numpy(group),
                int(group[-1]) + 1,
            )
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
        if evaluate is None:
            continue
        score = evaluate(model)
        scores.append(score)
        if score > best_score:
            best_score, best_state = score, copy.deepcopy(net.state_dict())
        elif epoch - int(np.argmax(scores)) >= patience:
            break
    if best_state is not None:
        net.load_state_dict(best_state)
    net.eval()
    return model, scores


def train_fold_lstm(
    frame: TrainingFrame,
    fit: slice,
    valid: slice,
    out_dir: Path,
    *,
    full: Optional[slice],
    objective: str,
    seeds: Sequence[int],
    params: dict[str, Any],
    min_period_rows: int,
    rel_prefix: str,
) -> FoldResult:
    if objective != "ic_ir":
        raise ValueError(f"LSTM 后端只支持 objective='ic_ir'，收到 {objective!r}")
    if frame.inputs is None or frame.source_rows is None:
        raise ValueError("LSTM 要取历史特征序列，训练集必须带 inputs / source_rows（dataset.build_training_frame 会填）")
    if int(params.get("num_threads", 0)) > 0:
        torch.set_num_threads(int(params["num_threads"]))

    valid_obj = ICIRObjective(frame.y[valid], frame.weights[valid], period_starts(frame.times[valid].asi8),
                              min_period_rows=min_period_rows)

    def evaluate(model: LSTMModel) -> float:
        return valid_obj.ic_ir(_predict_rows(model, frame, valid))

    out_dir.mkdir(parents=True, exist_ok=True)
    files, best, scores = [], [], []
    for seed in seeds:
        # ① 早停：找最佳 epoch 数
        stopped, history = _train_net(frame, fit, params, seed=seed, epochs=int(params["max_epochs"]),
                                      min_period_rows=min_period_rows, evaluate=evaluate, patience=int(params["patience"]))
        epochs = int(np.argmax(history)) + 1
        # ② 重训：整个训练窗口，同一个种子，固定 epoch 数
        final = stopped if full is None else _train_net(frame, full, params, seed=seed, epochs=epochs,
                                                        min_period_rows=min_period_rows)[0]
        path = out_dir / f"seed{seed}.pt"
        save_checkpoint(path, final)
        files.append(f"{rel_prefix}/{path.name}")
        best.append(epochs)
        scores.append(float(max(history)))

    return FoldResult(
        files=files,
        best_iterations=best,
        metrics={
            "inner_valid_ic_ir_by_seed": scores,
            "n_fit_rows": fit.stop - fit.start,
            "n_refit_rows": None if full is None else full.stop - full.start,
        },
    )
