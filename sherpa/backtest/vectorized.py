"""第二层·向量化入口（设计文档 §8.4.2）。"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel, interval_to_timedelta
from sherpa.metrics.performance import calmar_ratio, equity_curve, max_drawdown, sharpe_ratio

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
    rebalance_every: int = 1,
) -> BacktestResult:
    """`docs/backtest_principle.md` 第二层，向量化版本。

    **时间标签口径：第 t 行 = t 时刻决策的持仓，赚它持有期内实现的收益**——跟研究里 IC 标签
    `sherpa.metrics.factor.forward_returns` 同一个口径：把未来的收益往前拉到决策那一行上，而不是把
    t 时刻的权重往后推到收益实现的那一行。这样第 t 行的 alpha、regime 状态、目标权重、收益都在同一行，
    可以直接对齐；按时间切段（选择段 / 验证段）时切的也是"决策发生在哪一段"。

    `shift` 是 §2(1) 的因果律对齐：t 收盘算出的目标权重，赚的是 `close[t+shift-1] -> close[t+shift]`
    那根 bar 的收益（`close.pct_change().shift(-shift)`）。`shift=1` 是收盘即成交；要跟 IC 标签的执行
    延迟 `delay` 对齐，取 `shift = 1 + delay`。它跟 `MarketEvent.bar_end_time`（§5.4）不是同一层约束，
    那个保证的是"单根 bar 内不能用收盘价无损入场"，两者都要满足。最后 `shift` 行的收益还没实现（数据
    里没有那么远的收盘价），不出现在结果里。

    `rebalance_every`：每隔几根 bar 调一次仓（按 `alpha_history` 的行号，第 0、N、2N…… 行）。
    非调仓的 bar **不交易**：持仓就是上一期的持仓按价格漂移后的样子，换手为 0、不扣成本。
    这跟"把目标权重前向填充"不一样——那样每根 bar 都会把漂移掉的部分配平回目标，产生一笔
    额外的小换手。`rebalance_every=1` 就是逐 bar 调仓。

    收益率口径：用 `panel.close` 的逐期变化率作为"这根 bar 的已实现收益"，这是向量化回测的标准
    简化——更贴近开盘价撮合的精确模型留给事件驱动路径（§8.4.3）按需实现，不在这里增加复杂度。

    逐 bar 的漂移 / 换手 / 成本递推用 numpy 数组实现，口径跟 `sherpa.portfolio.turnover` 的
    `drift_weights` / `turnover` 完全一致（`tests/backtest/test_vectorized.py` 保留了逐 bar 调用
    这两个函数的旧写法做对比）；只是避免每根 bar 都做一次 pandas 按 symbol 对齐——关卡3 要对
    几百种组合各跑一遍全研究段，旧写法太慢。
    """
    if shift < 1:
        raise ValueError(f"shift 至少是 1（shift=0 等于用决策之前已经实现的收益，是前视），收到 {shift}")
    if rebalance_every < 1:
        raise ValueError(f"rebalance_every 至少是 1，收到 {rebalance_every}")

    columns = panel.close.columns
    rebalance_rows = np.arange(len(alpha_history.index)) % rebalance_every == 0
    # 只在调仓行调用 weighting_fn：非调仓行的目标权重用不到。
    target_values = np.zeros((len(alpha_history.index), len(columns)))
    for i in np.flatnonzero(rebalance_rows):
        target_values[i] = weighting_fn(alpha_history.iloc[i]).reindex(columns).to_numpy(dtype=float)
    target_weights = pd.DataFrame(target_values, index=alpha_history.index, columns=columns)
    trade_flags = pd.Series(rebalance_rows, index=alpha_history.index)

    # t 行 = t 时刻决策的持仓在持有期内实现的收益：(close[t+shift] - close[t+shift-1]) / close[t+shift-1]。
    # 价格序列最后 shift 行还没有实现的收益，去掉。
    forward_returns = panel.close.pct_change().shift(-shift).iloc[:-shift]
    common_index = target_weights.index.intersection(forward_returns.index)
    if isinstance(common_index, pd.DatetimeIndex):
        # 不带 freq，跟事件驱动路径（逐 bar 收集时间戳）产出的 index 口径一致，方便逐期交叉验证。
        common_index = common_index.copy()
        common_index.freq = None
    weights = target_weights.loc[common_index].fillna(0.0).to_numpy(dtype=float)
    returns = forward_returns.loc[common_index].fillna(0.0).to_numpy(dtype=float)
    trade = trade_flags.loc[common_index].to_numpy(dtype=bool)

    net_returns = np.empty(len(common_index))
    turnovers = np.empty(len(common_index))

    # 调仓时要跟"上一期持仓漂移到现在的样子"比：上一期持仓在它自己的持有期里实现的收益，正好是
    # 上一行的 forward return（`prev_return`），不是这一行的——用错会导致换手算多/算少（这个坑已经在
    # event_driven.py 的实现/文档里踩过一次，两边写法要保持一致，见 §8.4.4 决策2）。
    prev_weights = np.zeros(len(columns))
    prev_return = np.zeros(len(columns))

    for i in range(len(common_index)):
        drifted = _drift(prev_weights, prev_return)
        held = weights[i] if trade[i] else drifted  # 不调仓的 bar 直接持有漂移后的仓位
        turnover = float(np.abs(held - drifted).sum())
        gross = float(held @ returns[i])

        net_returns[i] = gross - cost_model.cost(turnover)
        turnovers[i] = turnover
        prev_weights = held
        prev_return = returns[i]

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


def _drift(prev_weights: np.ndarray, period_returns: np.ndarray) -> np.ndarray:
    """`sherpa.portfolio.turnover.drift_weights` 的 numpy 版本（两边已按同一组 symbol 对齐、NaN 已填 0）。"""
    gross_exposure = float(np.abs(prev_weights).sum())
    if gross_exposure == 0.0:
        return prev_weights.copy()
    drifted_value = prev_weights * (1.0 + period_returns)
    drifted_exposure = float(np.abs(drifted_value).sum())
    if drifted_exposure == 0.0:
        return np.zeros_like(prev_weights)
    return drifted_value / drifted_exposure * gross_exposure
