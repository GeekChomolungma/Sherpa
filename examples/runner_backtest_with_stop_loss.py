"""示例：Runner + 事件驱动回测——带状态的止损策略。

演示如何用完整的编排链路（`BaseStrategy` -> `Runner` -> `AlphaEngine` -> `BacktestSink`
-> `Simulator`）跑一个向量化路径做不到的策略：持仓期间浮亏超过阈值就无条件止损平仓。

止损是路径依赖逻辑——判断依据是"这笔仓位是什么时候、什么价位建的"，这是跨 bar 的状态。
`sherpa.backtest.vectorized.run_vectorized_backtest` 的 `weighting_fn` 签名只接收单根
截面的 alpha 分数，没有地方存这种状态；`BaseStrategy.on_bar()` 是对象方法，`self` 上
可以存任意状态，`Runner` 又是逐 bar 顺序调用它，所以这类逻辑只能写在这里（对比
examples/vectorized_research.py 里同样的动量因子，没有止损时向量化路径就够用）。

不连接真实 ClickHouse——用 `FakeClickHouseClient` 站台，除了这一处，其余全部是生产代码：
`CHReader`/`Universe`/`HistoricalPanelSource` 都是 `sherpa.data` 的真实实现，真实环境
换成 `clickhouse_connect.get_client(...)` 即可，不需要改上层任何代码。

运行：
    python examples/runner_backtest_with_stop_loss.py
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from sherpa.alpha.base import custom_alpha
from sherpa.alpha.engine import AlphaEngine
from sherpa.backtest.cost_model import FixedFeeCostModel
from sherpa.backtest.event_driven import Simulator
from sherpa.data.ch_reader import CHReader
from sherpa.data.panel_source import HistoricalPanelSource
from sherpa.data.schema import MarketEvent
from sherpa.data.universe import Universe
from sherpa.portfolio.weighting import top_k_long_short
from sherpa.strategy.base import BaseStrategy
from sherpa.strategy.runner import Runner
from sherpa.strategy.schema import TargetPosition
from sherpa.strategy.sink import BacktestSink

from _synthetic_market import FakeClickHouseClient, close_to_ch_long_df, make_synthetic_ohlcv

MOMENTUM_LOOKBACK = 60
ALPHA_NAME = f"custom.momentum_{MOMENTUM_LOOKBACK}"
STOP_LOSS_PCT = 0.05  # 单个 symbol 浮亏超过 5%（相对建仓价、按持仓方向算）无条件平仓
TOP_K = 3


@custom_alpha(f"momentum_{MOMENTUM_LOOKBACK}", min_lookback=MOMENTUM_LOOKBACK + 1)
def momentum(panel):
    """过去 N 根的累计收益率——最简单的截面动量因子，跟 vectorized_research.py 用的是同一个。"""
    return panel.close.pct_change(MOMENTUM_LOOKBACK)


class StopLossMomentumStrategy(BaseStrategy):
    """动量选股 + Top-K 多空 + 无条件止损。

    `top_k_long_short` 这一步用的是 `sherpa.portfolio.weighting` 里跟向量化路径完全同一个
    函数——权重映射口径要一致（设计文档 §8.3 决策1）。止损是这个类自己加的、映射函数覆盖
    不到的额外逻辑。
    """

    strategy_id = "stop_loss_momentum"

    def setup(self) -> None:
        self._entry_prices: dict[str, float] = {}
        self._last_weights: dict[str, float] = {}

    def on_bar(self, event: MarketEvent, features: pd.DataFrame) -> TargetPosition:
        alpha_scores = features[ALPHA_NAME]
        target = dict(top_k_long_short(alpha_scores, k=TOP_K))
        current_prices = event.panel.close.iloc[-1]

        # 止损：对已经持仓的 symbol，按持仓方向算浮盈浮亏，跌破阈值就强制平掉——不管
        # momentum 因子这时候怎么说。这份状态（entry_prices）只有 on_bar 能维护。
        for symbol, entry_price in list(self._entry_prices.items()):
            price_now = current_prices.get(symbol)
            if price_now is None or pd.isna(price_now):
                continue
            direction = 1.0 if self._last_weights.get(symbol, 0.0) > 0 else -1.0
            pnl_pct = (price_now / entry_price - 1.0) * direction
            if pnl_pct <= -STOP_LOSS_PCT:
                target[symbol] = 0.0
                del self._entry_prices[symbol]

        # 记录新建仓位的入场价，平仓的 symbol 不需要保留
        for symbol, weight in target.items():
            if weight != 0.0 and symbol not in self._entry_prices:
                price_now = current_prices.get(symbol)
                if price_now is not None and not pd.isna(price_now):
                    self._entry_prices[symbol] = price_now

        self._last_weights = target
        return TargetPosition(target)


def main() -> None:
    close, _mus = make_synthetic_ohlcv(n_symbols=10, n_bars=500, mu_spread=0.004, noise_std=0.01, seed=0)
    long_df = close_to_ch_long_df(close)

    ch_reader = CHReader(FakeClickHouseClient(long_df))
    universe = Universe(list(close.columns), ch_reader=ch_reader)
    panel_source = HistoricalPanelSource(
        ch_reader,
        universe=universe,
        interval="1m",
        start_time=close.index[MOMENTUM_LOOKBACK + 10],
        end_time=close.index[-1],
        lookback_bars=MOMENTUM_LOOKBACK + 5,
    )

    alpha_engine = AlphaEngine([momentum()])
    cost_model = FixedFeeCostModel(fee_bps=5)
    simulator = Simulator(prices=close, cost_model=cost_model, interval="1m")
    runner = Runner(StopLossMomentumStrategy(), alpha_engine, BacktestSink(simulator))

    runner.run_backtest(panel_source)

    result = simulator.result()
    print(f"跑了 {len(result.returns)} 根 bar")
    print(f"最终净值:     {result.equity_curve.iloc[-1]:.4f}")
    print(f"年化 Sharpe:  {result.sharpe:.2f}（合成数据信噪比远高于真实市场，这个数字不代表真实策略水平）")
    print(f"Calmar:       {result.calmar:.2f}")
    print(f"最大回撤:     {result.max_drawdown:.2%}")
    print(f"平均单期换手: {result.turnover.mean():.2%}")


if __name__ == "__main__":
    main()
