"""第一层入口（设计文档 §8.4.1）：只做统计检验，不碰仓位/成本。"""

from __future__ import annotations

import pandas as pd

from sherpa.metrics.factor import ic_summary, is_monotonic_decreasing, quantile_returns, rank_ic

from .result import AlphaCheckResult


def run_alpha_check(
    alpha_history: pd.DataFrame,
    forward_returns: pd.DataFrame,
    *,
    n_quantiles: int = 10,
    ic_ir_threshold: float = 0.5,
) -> AlphaCheckResult:
    """`docs/backtest_principle.md` 第一层：RankIC + IC_IR + 分位数单调性一票否决。

    `ic_ir_threshold` 不写死常量——不同频率因子的合理阈值差很多（日频通常要求 IC 均值
    >0.03~0.05，分钟级 0.01~0.02 就有价值），由调用方按自己的因子频率传入。`passed` 同时
    要求 IC_IR 达标 *和* 分位数单调（组1多头到组K空头的均值收益非递增）——只满足其中一个
    不代表因子真的可靠：IC_IR 高但分组收益中间乱掉，说明区分度有结构性缺陷。
    """
    ic_series = rank_ic(alpha_history, forward_returns)
    summary = ic_summary(ic_series)
    q_returns = quantile_returns(alpha_history, forward_returns, n_quantiles=n_quantiles)
    monotonic = is_monotonic_decreasing(q_returns.mean(axis=0))
    passed = (not pd.isna(summary.ic_ir)) and summary.ic_ir >= ic_ir_threshold and monotonic
    return AlphaCheckResult(
        ic_series=ic_series,
        ic_mean=summary.mean,
        ic_std=summary.std,
        ic_ir=summary.ic_ir,
        quantile_returns=q_returns,
        passed=passed,
    )
