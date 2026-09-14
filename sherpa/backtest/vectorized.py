"""第二层·向量化入口（设计文档 §8.4.2）。"""

from __future__ import annotations

from typing import Callable

import pandas as pd

from sherpa.data.schema import BarPanel, interval_to_timedelta
from sherpa.metrics.performance import calmar_ratio, equity_curve, max_drawdown, sharpe_ratio
from sherpa.portfolio.turnover import drift_weights
from sherpa.portfolio.turnover import turnover as compute_turnover

from .cost_model import CostModel
from .result import BacktestResult

_YEAR = pd.Timedelta(days=365)


def run_vectorized_backtest(
    alpha_history: pd.DataFrame,
    panel: BarPanel,
    weighting_fn: Callable[[pd.Series], pd.Series],
    cost_model: CostModel,
    *,
    shift: int = 1,
) -> BacktestResult:
    """`docs/backtest_principle.md` 第二层，向量化版本。

    `shift` 是 §2(1) 的因果律对齐：`weighting_fn` 逐期作用在 `alpha_history` 上产出的目标
    权重，要整体往后移 `shift` 期才生效——跟 `MarketEvent.bar_end_time`（§5.4）不是同一层
    约束，那个保证的是"单根 bar 内不能用收盘价无损入场"，这里保证的是"权重矩阵本身要比
    alpha 矩阵晚一期"，两者都要满足。

    收益率口径：用 `panel.close` 的逐期变化率（`pct_change()`）作为"这根 bar 的已实现收益"，
    这是向量化回测的标准简化——更贴近开盘价撮合的精确模型留给事件驱动路径（§8.4.3）按需
    实现，不在这里增加复杂度。
    """
    target_weights = pd.DataFrame({t: weighting_fn(alpha_history.loc[t]) for t in alpha_history.index}).T
    target_weights = target_weights.reindex(columns=panel.close.columns, fill_value=0.0)
    effective_weights = target_weights.shift(shift)

    period_returns = panel.close.pct_change()

    common_index = effective_weights.index.intersection(period_returns.index)
    effective_weights = effective_weights.loc[common_index]
    period_returns = period_returns.loc[common_index]

    net_returns: list[float] = []
    turnovers: list[float] = []
    prev_weights = pd.Series(0.0, index=panel.close.columns)
    # `prev_weights` 是在*上一根* bar 才生效持有的权重，真正漂移它要用上一根 bar 自己实现的
    # 收益率，不是当前这根——这两根 bar 的收益率通常不同，用错会导致换手算多/算少（这个坑
    # 已经在 event_driven.py 的实现/文档里踩过一次，这里的写法要跟它保持一致，见 §8.4.4 决策2）。
    prev_return = pd.Series(0.0, index=panel.close.columns)

    for t in common_index:
        w_t = effective_weights.loc[t].fillna(0.0)
        r_t = period_returns.loc[t]
        drifted = drift_weights(prev_weights, prev_return)
        to = compute_turnover(w_t, drifted)
        gross = float((w_t * r_t.fillna(0.0)).sum())
        cost = cost_model.cost(to)

        net_returns.append(gross - cost)
        turnovers.append(to)
        prev_weights = w_t
        prev_return = r_t.fillna(0.0)

    net_series = pd.Series(net_returns, index=common_index, name="net_return")
    turnover_series = pd.Series(turnovers, index=common_index, name="turnover")

    periods_per_year = _YEAR / interval_to_timedelta(panel.interval)
    curve = equity_curve(net_series)
    return BacktestResult(
        equity_curve=curve,
        returns=net_series,
        turnover=turnover_series,
        sharpe=sharpe_ratio(net_series, periods_per_year=periods_per_year),
        calmar=calmar_ratio(net_series, periods_per_year=periods_per_year),
        max_drawdown=max_drawdown(curve),
    )
