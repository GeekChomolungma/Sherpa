"""LightGBM 后端的单个重训时点训练（V1–V4 的训练方式，逻辑跟拆分前逐行相同）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional, Sequence

from dataset import TrainingFrame
from trainers.common import FoldResult, objective_for


def lgb_feature_names(names: Sequence[str]) -> list[str]:
    """LightGBM 的特征名不能有 JSON 特殊字符（比如 `alpha:worldquant.alpha040` 里的冒号），换成下划线。只影响模型文件
    里记录的名字；推断按列的位置喂数据，顺序由 `FeatureSpec.feature_names` 固定。"""
    return [re.sub(r"[^0-9A-Za-z_]", "_", name) for name in names]


def _train_set(frame: TrainingFrame, rows: slice, objective: str, lgb_params: dict[str, Any], min_period_rows: int):
    """一段行 -> (LightGBM 数据集, 训练参数)。IC_IR 损失要绑定这段行自己的标签和期分组，所以每段各建一次。"""
    import lightgbm as lgb  # noqa: PLC0415

    names = lgb_feature_names(frame.feature_names)
    if objective == "ic_ir":
        obj = objective_for(frame, rows, min_period_rows)
        dataset = lgb.Dataset(frame.features[rows], label=frame.y[rows], feature_name=names, free_raw_data=False)
        return dataset, {**lgb_params, "objective": obj.lgb_objective, "metric": "None"}
    if objective == "l2_rank":
        dataset = lgb.Dataset(
            frame.features[rows], label=frame.y[rows], weight=frame.weights[rows], feature_name=names, free_raw_data=False
        )
        return dataset, {**lgb_params, "objective": "regression", "metric": "None"}
    raise ValueError(f"未知的 OBJECTIVE：{objective!r}")


def train_fold_lightgbm(
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
    import lightgbm as lgb  # noqa: PLC0415

    valid_obj = objective_for(frame, valid, min_period_rows)
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
