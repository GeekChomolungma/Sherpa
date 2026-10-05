"""关卡3 自己的纯函数：按冻结配方重建合成分数、按 validation_start 切段。

打分 → 目标仓位 → 扣费回测 → 分段绩效这条链（`cross_sectional_rank` / `target_path` / `segment_stats` 等）
在 `sherpa.backtest.score_backtest`，关卡3 和 ML 探索实验（`research/ml_training/evaluation.py`）共用，这里
re-export 前三个，保持 `from signals import ...` 的老写法可用。

合成部分（`weighted_composite` / 路由）从 `research/factor_synthesis/signals.py` 拷贝后独立维护（research 子项目
之间不互相 import），口径必须跟关卡2 保持一致：关卡3 回测的就是关卡2 在验证段上比较过的那个分数，差一点就不是
同一个信号了。不同的是**权重不再在这里估计**——方向、权重都已经由上游（关卡2 或它的透传）写进研究线的配方交接
文件（`handoff/synthesis.json`），这里只照配方复现。

矩阵约定跟 sherpa 其余部分一致：`(T, N)` DataFrame，行 = bar 时间，列 = symbol。
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from sherpa.backtest.score_backtest import (  # noqa: F401  re-export，保持 `from signals import ...` 的老写法可用
    cross_sectional_rank,
    segment_stats,
    target_path,
    weighted_composite,
)


# ---------------------------------------------------------------------------
# 按配方重建合成分数（口径同关卡2）
# ---------------------------------------------------------------------------


def case_scores(case: Mapping[str, Any], ranked: Mapping[str, pd.DataFrame], regime: pd.DataFrame) -> pd.DataFrame:
    """按配方交接文件里一个配方算出合成分数。

    - `kind="static"`：全程同一组权重（G0 / L1 / L0 / 单因子参照）；
    - `kind="routed"`：每根 bar 按它所处的 `dimension` state 选那个 state 的权重；state 未知（滚动窗口
      warm-up）或该 state 没有配方时退回 `fallback` 的权重——跟关卡2 `routed_composite` 的规则一致。
      `fallback` 为空时这些 bar 的分数是 NaN（不持仓）。
      regime 标签是 point-in-time 的（滚动分位数只看 <= t 的数据），路由不引入未来信息。
    """
    if case["kind"] == "static":
        return weighted_composite(ranked, case["weights"])
    if case["kind"] != "routed":
        raise ValueError(f"未知的 case kind：{case['kind']!r}")

    fallback = case.get("fallback") or {}
    if any(w != 0.0 for w in fallback.values()):
        result = weighted_composite(ranked, fallback)
    else:
        template = next(iter(ranked.values()))
        result = pd.DataFrame(np.nan, index=template.index, columns=template.columns)
    labels = regime[case["dimension"]]
    for state, weights in case["states"].items():
        if not any(w != 0.0 for w in weights.values()):
            continue
        rows = (labels == state).fillna(False).reindex(result.index, fill_value=False)
        if not rows.any():
            continue
        result.loc[rows] = weighted_composite(ranked, weights).loc[rows]
    return result


# ---------------------------------------------------------------------------
# 按决策时点切段
# ---------------------------------------------------------------------------


def segment_masks(index: pd.DatetimeIndex, validation_start: pd.Timestamp) -> dict[str, pd.Series]:
    """把研究段切成选择段 / 验证段两个布尔掩码，按**决策时点**切。

    回测结果的第 t 行是 t 时刻决策的持仓赚到的收益（`run_vectorized_backtest` 的时间标签口径），跟关卡2
    IC 序列的第 t 行（t 时刻的分数 vs 它的未来收益标签）是同一个时点，所以两关按同一个 `validation_start`
    切出来的是同一批决策。

    跟关卡2 不同，这里不 purge 边界：关卡2 的 purge 是为了不让"估方向用的标签"伸进验证段；关卡3 不在
    任何一段上估参数，配方在跑回测之前就已冻结，两段只是分开统计同一条连续的持仓路径。
    """
    in_validation = pd.Series(index >= validation_start, index=index)
    return {"selection(样本内参考)": ~in_validation, "validation(方案比较)": in_validation}

