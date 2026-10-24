"""XGBoost 后端的单个重训时点训练：流程、损失、早停指标跟 `lgb.py` 一一对应。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

from dataset import TrainingFrame
from trainers.common import FoldResult, objective_for


def _xgb_matrix(frame: TrainingFrame, rows: slice, objective: str):
    import xgboost as xgb  # noqa: PLC0415

    weight = frame.weights[rows] if objective == "l2_rank" else None
    return xgb.DMatrix(frame.features[rows], label=frame.y[rows], weight=weight, missing=np.nan)


def _xgb_objective(frame: TrainingFrame, rows: slice, objective: str, min_period_rows: int):
    """XGBoost 的自定义损失跟 LightGBM 同一个签名 `(preds, data) -> (grad, hess)`，直接复用 `ICIRObjective.lgb_objective`。"""
    if objective == "ic_ir":
        return objective_for(frame, rows, min_period_rows).lgb_objective, {}
    if objective == "l2_rank":
        return None, {"objective": "reg:squarederror"}
    raise ValueError(f"未知的 OBJECTIVE：{objective!r}")


def train_fold_xgboost(
    frame: TrainingFrame,
    fit: slice,
    valid: slice,
    out_dir: Path,
    *,
    full: Optional[slice],
    objective: str,
    seeds: Sequence[int],
    params: dict[str, Any],
    num_boost_round: int,
    early_stopping_rounds: int,
    min_period_rows: int,
    rel_prefix: str,
) -> FoldResult:
    """XGBoost 版两步训练，流程、损失、早停指标跟 `_train_lightgbm` 一一对应。

    XGBoost 的 `best_iteration` 是从 0 数的下标，这里统一换成"保留几棵树"（跟 LightGBM 的 `best_iteration` 同义）。
    """
    import xgboost as xgb  # noqa: PLC0415

    valid_obj = objective_for(frame, valid, min_period_rows)

    def metric(preds: np.ndarray, _data) -> tuple[str, float]:
        return "ic_ir", valid_obj.ic_ir(preds)

    fit_set = _xgb_matrix(frame, fit, objective)
    fit_obj, fit_extra = _xgb_objective(frame, fit, objective, min_period_rows)
    valid_set = _xgb_matrix(frame, valid, objective)
    if full is not None:
        full_set = _xgb_matrix(frame, full, objective)
        full_obj, full_extra = _xgb_objective(frame, full, objective, min_period_rows)

    out_dir.mkdir(parents=True, exist_ok=True)
    files, best, scores = [], [], []
    for seed in seeds:
        stopped = xgb.train(
            {**params, **fit_extra, "seed": seed},
            fit_set,
            num_boost_round=num_boost_round,
            evals=[(valid_set, "inner_valid")],
            obj=fit_obj,
            custom_metric=metric,
            maximize=True,
            early_stopping_rounds=early_stopping_rounds,
            verbose_eval=False,
        )
        iteration = int(stopped.best_iteration) + 1
        if full is None:
            final = stopped[:iteration]
        else:
            final = xgb.train({**params, **full_extra, "seed": seed}, full_set, num_boost_round=iteration, obj=full_obj)
        path = out_dir / f"seed{seed}.json"
        final.save_model(str(path))
        files.append(f"{rel_prefix}/{path.name}")
        best.append(iteration)
        scores.append(float(stopped.best_score))

    return FoldResult(
        files=files,
        best_iterations=best,
        metrics={
            "inner_valid_ic_ir_by_seed": scores,
            "n_fit_rows": fit.stop - fit.start,
            "n_refit_rows": None if full is None else full.stop - full.start,
        },
    )
