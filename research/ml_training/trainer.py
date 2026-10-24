"""单个重训时点训练的统一入口 + 样本外评估指标。纯函数，不连数据库、不读写清单——编排在 `run_training.py`。

`train_fold` 按模型后端（`config.BACKEND` / 模型的 `training_overrides["backend"]`）分派到 `trainers/` 下对应的文件
（一种架构一个文件，见 `trainers/__init__.py`），模型文件格式跟推断端 `sherpa/alpha/custom/ml/backends/` 对应。
ML 库在用到时才 import：只装了 lightgbm 也能训练 / 测试 LightGBM 模型。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from dataset import TrainingFrame
from objective import ICIRObjective, period_starts
from trainers.common import FoldResult  # noqa: F401  老写法 `from trainer import FoldResult` 继续可用


def train_fold(
    frame: TrainingFrame,
    fit: slice,
    valid: slice,
    out_dir: Path,
    *,
    full: Optional[slice],
    objective: str,
    seeds: Sequence[int],
    lgb_params: dict[str, Any],
    num_boost_round: int,
    early_stopping_rounds: int,
    min_period_rows: int,
    rel_prefix: str,
    backend: str = "lightgbm",
    backend_params: Optional[Mapping[str, Any]] = None,
) -> FoldResult:
    """一个重训时点的训练，每个随机种子两步：

    ① 早停：在拟合段 `fit` 上训练，每加一棵树（LSTM：每过一个 epoch）就在内部验证段 `valid` 上算一次 IC_IR，连续
       `early_stopping_rounds`（LSTM：`patience`）轮没刷新最好成绩就停，得到最佳轮数；
    ② 重训：用整个训练窗口 `full`（拟合段 + 间隔 + 验证段）按最佳轮数重新训练，不再早停，保存这一步的模型。
       验证段只负责回答"训练几轮"，答完也参与训练——模型学到的数据一直到训练窗口末尾，不用隔着验证段去预测。
       `full=None` 时跳过这一步，直接保存第①步的模型（旧行为）。

    `lgb_params` 只给 LightGBM；其它后端的超参数是 `backend_params`（`config.for_model` 合并好的有效值）。
    """
    common = dict(full=full, objective=objective, seeds=seeds, min_period_rows=min_period_rows, rel_prefix=rel_prefix)
    if backend == "lightgbm":
        from trainers.lgb import train_fold_lightgbm  # noqa: PLC0415

        return train_fold_lightgbm(frame, fit, valid, out_dir, lgb_params=lgb_params, num_boost_round=num_boost_round,
                               early_stopping_rounds=early_stopping_rounds, **common)
    if backend == "xgboost":
        from trainers.xgb import train_fold_xgboost  # noqa: PLC0415

        return train_fold_xgboost(frame, fit, valid, out_dir, params=dict(backend_params or {}), num_boost_round=num_boost_round,
                              early_stopping_rounds=early_stopping_rounds, **common)
    if backend == "lstm":
        from trainers.lstm import train_fold_lstm  # noqa: PLC0415  torch 只在训练 LSTM 时才需要

        return train_fold_lstm(frame, fit, valid, out_dir, params=dict(backend_params or {}), **common)
    raise ValueError(f"未知的模型后端 {backend!r}")


def spearman_by_period(pred: np.ndarray, label: np.ndarray, times: pd.DatetimeIndex, *, min_period_rows: int) -> pd.Series:
    """逐期 Spearman RankIC（等权，跟研究流水线的 `rank_ic` 同一个定义，只是输入是长表）。"""
    ranks = pd.DataFrame({"p": pred, "y": label, "t": times.asi8})
    ranked = ranks.groupby("t")[["p", "y"]].rank()
    starts = period_starts(ranks["t"].to_numpy())
    obj = ICIRObjective(ranked["y"].to_numpy(), np.ones(len(ranks)), starts, min_period_rows=min_period_rows)
    ic = obj.ic_series(ranked["p"].to_numpy())
    return pd.Series(ic, index=pd.DatetimeIndex(times[starts]))


def ic_stats(ic: pd.Series) -> dict[str, float]:
    ic = ic.dropna()
    std = ic.std()
    return {
        "periods": int(len(ic)),
        "rank_ic_mean": float(ic.mean()) if len(ic) else float("nan"),
        "rank_ic_ir": float(ic.mean() / std) if len(ic) > 1 and std > 0 else float("nan"),
        "rank_ic_win_rate": float((ic > 0).mean()) if len(ic) else float("nan"),
    }
