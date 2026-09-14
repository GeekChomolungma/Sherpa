"""第二层·事件驱动入口（设计文档 §8.4.3）：`BacktestSink` 唯一直接持有/调用的对象。"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

import pandas as pd

from sherpa.data.schema import interval_to_timedelta
from sherpa.metrics.performance import calmar_ratio, equity_curve, max_drawdown, sharpe_ratio
from sherpa.portfolio.turnover import drift_weights
from sherpa.portfolio.turnover import turnover as compute_turnover

from .cost_model import CostModel
from .result import BacktestResult

_YEAR = pd.Timedelta(days=365)


@runtime_checkable
class TargetIntent(Protocol):
    """`Simulator` 需要的最小信号形状——结构类型，不 import `sherpa.strategy.SignalIntent`。

    `sherpa.backtest` 不依赖 `sherpa.strategy` 的任何东西（设计文档 §8.4.4 决策1）；真正的
    `SignalIntent` 天然满足这个 Protocol（鸭子类型），`BacktestSink` 转发过来的对象不需要
    做任何转换。
    """

    symbol: str
    target_percent: float
    bar_end_time: pd.Timestamp


class Simulator:
    """吃 `SignalIntent` 流，维护持仓/资金状态，产出跟向量化路径同形状的 `BacktestResult`。

    `intents` 里没有价格——协议要跟 `WebhookSink` 共用同一个签名（设计文档 §8.4.3 决策）。
    所以价格必须在构造时单独注入：`prices` 是覆盖整个回测区间的 `(T,N)` 收盘价 DataFrame
    （跟 `BacktestSink` 那次回测用的是同一个 `panel.close`）。
    """

    def __init__(
        self,
        *,
        prices: pd.DataFrame,
        cost_model: CostModel,
        initial_capital: float = 1.0,
        interval: str = "1m",
    ):
        self._prices = prices
        self._returns = prices.pct_change()
        self._cost_model = cost_model
        self._initial_capital = initial_capital
        self._interval = interval
        self._prev_weights = pd.Series(0.0, index=prices.columns)
        # 上一次调用算出来的换手，还没配对到它该扣减的那一期收益——见 on_intents 的说明。
        self._pending_turnover = 0.0
        self._net_returns: dict[pd.Timestamp, float] = {}
        self._turnovers: dict[pd.Timestamp, float] = {}

    def on_intents(self, intents: Sequence[TargetIntent]) -> None:
        """收到新一批目标权重（同一次 `on_bar` 产出，共享 `bar_end_time`）。

        **记账时点，容易搞反的地方**：本次收到的目标权重（`target_T`，从 bar T 的信息算出）
        要到*下一根* bar 才开始生效持有（shift-1）；但换算出这次调仓的换手量（把上一次持有的
        `target_{T-1}` 换成 `target_T`）所需要的价格变动，恰恰是 bar T 这一期*已经*实现的
        收益——这个信息现在就有，不用等下一次调用。于是这里分两步：

        1. **结算本期（bar T）的净收益**：用"上一次调用时算出、还没地方安放"的换手
           （`self._pending_turnover`，对应"把 `target_{T-2}` 换成 `target_{T-1}` 那笔调仓"）
           配上 `target_{T-1}`（`self._prev_weights`）在 bar T 里实际吃到的收益，正好对应
           `docs/backtest_principle.md` §2(5) "`Cost_{t+1}` 从 `R_{t+1}^gross` 里扣"这一步，
           只是这里的下标关系是靠"上一次调用缓存的换手"体现，不是同一次算出来就用。
        2. **计算这次调仓（`target_{T-1}` -> `target_T`）产生的换手，先缓存起来**：要用
           bar T 的实际收益率把 `target_{T-1}` 漂移到 `W_drift` 再跟 `target_T` 比——这笔换手
           要等*下一次*调用（bar T+1 结算时）才会被用掉，现在只是算出来存好。

        跟向量化路径（`vectorized.py`）逐行对比验证过两者数值完全一致（设计文档 §8.4.4
        决策2），这个"缓存一期换手"的写法不是随意选择，是为了复现向量化路径里
        `effective_weights = target_weights.shift(1)` 那次整体平移在流式场景下的等价效果。
        """
        if not intents:
            return
        bar_start_time = self._resolve_bar_start_time(intents[0].bar_end_time)
        new_target = pd.Series({intent.symbol: intent.target_percent for intent in intents})
        new_target = new_target.reindex(self._prices.columns, fill_value=0.0)

        period_return = self._returns.loc[bar_start_time] if bar_start_time in self._returns.index else None
        if period_return is None:
            period_return = pd.Series(0.0, index=self._prices.columns)

        gross = float((self._prev_weights * period_return.fillna(0.0)).sum())
        cost = self._cost_model.cost(self._pending_turnover)
        self._net_returns[bar_start_time] = gross - cost
        self._turnovers[bar_start_time] = self._pending_turnover

        drifted = drift_weights(self._prev_weights, period_return)
        self._pending_turnover = compute_turnover(new_target, drifted)
        self._prev_weights = new_target

    def result(self) -> BacktestResult:
        index = pd.DatetimeIndex(sorted(self._net_returns.keys()))
        net_series = pd.Series([self._net_returns[t] for t in index], index=index, name="net_return")
        turnover_series = pd.Series([self._turnovers[t] for t in index], index=index, name="turnover")

        periods_per_year = _YEAR / interval_to_timedelta(self._interval)
        curve = equity_curve(net_series, initial_capital=self._initial_capital)
        return BacktestResult(
            equity_curve=curve,
            returns=net_series,
            turnover=turnover_series,
            sharpe=sharpe_ratio(net_series, periods_per_year=periods_per_year),
            calmar=calmar_ratio(net_series, periods_per_year=periods_per_year),
            max_drawdown=max_drawdown(curve),
        )

    def _resolve_bar_start_time(self, bar_end_time: pd.Timestamp) -> pd.Timestamp:
        """`bar_end_time = bar_start_time + interval - 1ms`（设计文档 §5.4），反解出 start_time
        用来跟 `self._prices`（index=start_time）对齐。"""
        return bar_end_time + pd.Timedelta(milliseconds=1) - interval_to_timedelta(self._interval)
