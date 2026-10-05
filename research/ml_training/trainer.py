"""单个重训时点的训练和评估（LightGBM）。纯函数，不连数据库、不读写清单——编排在 `run_training.py`。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

import lightgbm as lgb
import numpy as np
import pandas as pd

from dataset import TrainingFrame
from objective import ICIRObjective, period_starts


@dataclass
class FoldResult:
    files: list[str]
    best_iterations: list[int]
    metrics: dict[str, Any] = field(default_factory=dict)


def lgb_feature_names(names: Sequence[str]) -> list[str]:
    """LightGBM 的特征名不能有 JSON 特殊字符（比如 `alpha:worldquant.alpha040` 里的冒号），换成下划线。只影响模型文件
    里记录的名字；推断按列的位置喂数据，顺序由 `FeatureSpec.feature_names` 固定。"""
    return [re.sub(r"[^0-9A-Za-z_]", "_", name) for name in names]


def _objective_for(frame: TrainingFrame, rows: slice, min_period_rows: int) -> ICIRObjective:
    return ICIRObjective(
        frame.y[rows], frame.weights[rows], period_starts(frame.times[rows].asi8), min_period_rows=min_period_rows
    )


def _train_set(frame: TrainingFrame, rows: slice, objective: str, lgb_params: dict[str, Any], min_period_rows: int):
    """一段行 -> (LightGBM 数据集, 训练参数)。IC_IR 损失要绑定这段行自己的标签和期分组，所以每段各建一次。"""
    names = lgb_feature_names(frame.feature_names)
    if objective == "ic_ir":
        obj = _objective_for(frame, rows, min_period_rows)
        dataset = lgb.Dataset(frame.features[rows], label=frame.y[rows], feature_name=names, free_raw_data=False)
        return dataset, {**lgb_params, "objective": obj.lgb_objective, "metric": "None"}
    if objective == "l2_rank":
        dataset = lgb.Dataset(
            frame.features[rows], label=frame.y[rows], weight=frame.weights[rows], feature_name=names, free_raw_data=False
        )
        return dataset, {**lgb_params, "objective": "regression", "metric": "None"}
    raise ValueError(f"未知的 OBJECTIVE：{objective!r}")


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
) -> FoldResult:
    """一个重训时点的训练，每个随机种子两步：

    ① 早停：在拟合段 `fit` 上训练，每加一棵树就在内部验证段 `valid` 上算一次 IC_IR，连续 `early_stopping_rounds`
       轮没刷新最好成绩就停，得到最佳轮数（= 保留几棵树）；
    ② 重训：用整个训练窗口 `full`（拟合段 + 间隔 + 验证段）按最佳轮数重新训练，不再早停，保存这一步的模型。
       验证段只负责回答"训练几棵树"，答完也参与长树——模型学到的数据一直到训练窗口末尾，不用隔着验证段去预测。
       `full=None` 时跳过这一步，直接保存第①步的模型（旧行为）。
    """
    valid_obj = _objective_for(frame, valid, min_period_rows)
    fit_set, fit_params = _train_set(frame, fit, objective, lgb_params, min_period_rows)
    valid_set = lgb.Dataset(frame.features[valid], label=frame.y[valid], reference=fit_set, free_raw_data=False)
    if full is not None:
        full_set, full_params = _train_set(frame, full, objective, lgb_params, min_period_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    files, best, scores = [], [], []
    for seed in seeds:
        # ① 早停：找最佳轮数
        stopped = lgb.train(
            {**fit_params, "seed": seed},
            fit_set,
            num_boost_round=num_boost_round,
            valid_sets=[valid_set],
            valid_names=["inner_valid"],
            feval=valid_obj.lgb_metric,
            callbacks=[lgb.early_stopping(early_stopping_rounds, first_metric_only=True, verbose=False)],
        )
        iteration = stopped.best_iteration or num_boost_round
        # ② 重训：整个训练窗口，固定轮数
        final = stopped if full is None else lgb.train({**full_params, "seed": seed}, full_set, num_boost_round=iteration)
        path = out_dir / f"seed{seed}.txt"
        final.save_model(str(path), num_iteration=iteration)
        files.append(f"{rel_prefix}/{path.name}")
        best.append(int(iteration))
        scores.append(float(stopped.best_score["inner_valid"]["ic_ir"]))

    return FoldResult(
        files=files,
        best_iterations=best,
        metrics={
            "inner_valid_ic_ir_by_seed": scores,
            "n_fit_rows": fit.stop - fit.start,
            "n_refit_rows": None if full is None else full.stop - full.start,
        },
    )


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
