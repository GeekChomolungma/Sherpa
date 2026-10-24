"""所有模型后端共用的部分：模型输入 `ModelInputs`、后端接口 `Backend`、多种子集成 `predict_ensemble`。

输入（`ModelInputs`）对所有后端是同一份：`build_features` 产出的长表（每个 (bar, symbol) 一行、K 列）。

- **表格模型**（LightGBM / XGBoost）：每行只看自己这一行的 K 个特征；
- **序列模型**（LSTM）：每行看同一个 symbol 最近 `seq_len` 根 bar 的特征（含当前这根），形状 `(seq_len, K)`。
  只往回看，所以 point-in-time 不变：第 t 行的序列只用 `<= t` 的特征行。某根 bar 这个 symbol 没有特征行（还没上线、
  缺数据）时这一步记为"不存在"（`present = 0`、特征为 0）。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

DEFAULT_BACKEND = "lightgbm"


@dataclass(frozen=True)
class ModelInputs:
    """一次推断（或一次训练）用到的全部特征行。

    `matrix` 的第 i 行 = 特征长表的第 i 行，`time_pos` / `symbol_pos` 是它在面板 `(T, N)` 网格里的坐标；
    `grid[t, s]` 反过来是坐标 (t, s) 那一行的行号，没有这一行为 -1（序列模型取历史用）。
    """

    matrix: np.ndarray  # (n, K) float32
    time_pos: np.ndarray  # (n,) int64
    symbol_pos: np.ndarray  # (n,) int64
    grid: np.ndarray  # (T, N) int64

    @classmethod
    def from_features(cls, features: pd.DataFrame, bar_index: pd.Index, columns: pd.Index) -> "ModelInputs":
        times = features.index.get_level_values("start_time")
        symbols = features.index.get_level_values("symbol")
        time_pos = np.asarray(bar_index.get_indexer(times), dtype=np.int64)
        symbol_pos = np.asarray(columns.get_indexer(symbols), dtype=np.int64)
        if (time_pos < 0).any() or (symbol_pos < 0).any():
            raise ValueError("特征行的 (时间, symbol) 不在面板网格里")
        grid = np.full((len(bar_index), len(columns)), -1, dtype=np.int64)
        grid[time_pos, symbol_pos] = np.arange(len(features))
        return cls(features.to_numpy(dtype="float32"), time_pos, symbol_pos, grid)

    @property
    def n_features(self) -> int:
        return self.matrix.shape[1]

    def select_columns(self, cols: list[int]) -> "ModelInputs":
        return ModelInputs(self.matrix[:, cols], self.time_pos, self.symbol_pos, self.grid)

    def rows(self, rows: np.ndarray) -> np.ndarray:
        """表格模型的输入：`(len(rows), K)`。"""
        return self.matrix[rows]

    def sequences(self, rows: np.ndarray, length: int) -> tuple[np.ndarray, np.ndarray]:
        """序列模型的输入：`(len(rows), length, K)` 的特征（最后一步 = 当前行）和 `(len(rows), length)` 的"这一步有没有行"。

        不存在的步特征填 NaN（由调用方统一处理缺失），`present` 为 False。
        """
        rows = np.asarray(rows, dtype=np.int64)
        t = self.time_pos[rows][:, None] + np.arange(-(length - 1), 1)[None, :]  # 从最早一步到当前这根
        s = np.broadcast_to(self.symbol_pos[rows][:, None], t.shape)
        ids = np.where(t >= 0, self.grid[np.clip(t, 0, None), s], -1)
        present = ids >= 0
        x = self.matrix[np.where(present, ids, 0)]
        x[~present] = np.nan
        return x, present


class Backend:
    """一种模型架构的推断：`load(path)` 读一个模型文件，`predict(model, inputs, rows)` 给 `rows` 这些行打分。"""

    name: str
    suffix: str  # 模型文件扩展名（训练端保存时用同一个）

    def load(self, path: Path) -> Any:  # pragma: no cover - 接口
        raise NotImplementedError

    def predict(self, model: Any, inputs: ModelInputs, rows: np.ndarray) -> np.ndarray:  # pragma: no cover - 接口
        raise NotImplementedError

    def min_lookback_extra(self, params: Mapping[str, Any]) -> int:
        """除了特征本身的回看窗口，模型输入还要再往回看几根 bar（序列模型 = seq_len − 1）。"""
        return 0


def predict_ensemble(
    backend: Backend, model_dir: Path, files: list[str], inputs: ModelInputs, rows: np.ndarray,
    cache: dict[str, Any] | None = None,
) -> np.ndarray:
    """一个重训时点的多个种子模型各自打分、取平均（原始预测值平均，跟以往 LightGBM 的做法一致）。"""
    cache = {} if cache is None else cache
    preds = []
    for rel in files:
        model = cache.get(rel)
        if model is None:
            model = cache[rel] = backend.load(Path(model_dir) / rel)
        preds.append(backend.predict(model, inputs, rows))
    return np.mean(preds, axis=0)
