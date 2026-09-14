"""示例：`LogSink` 作为 paper trading —— `sherpa.live` 升级后的效果。

`LogSink` 现在不是简单转发 `Runner` 的原始输出，而是调用 `sherpa.live.build_live_requests`
把 `SignalIntent` 转成 `LiveOrderRequest` 再落日志（设计文档 §8.5.2/§9.1）：日志里能看到
确定性的幂等 key（`strategy_id:bar_end_time:symbol`）和这条信号真正被处理的时刻
（`dispatched_at`），这两个字段原始 `SignalIntent` 都不提供，只有接入实盘/Webhooker 才用
得上——这正是"`LogSink` 是 paper trading 默认实现"这句话的具体含义，不是简单转发。

这个示例走的是 `run_backtest`（用 `HistoricalPanelSource` 回放合成数据），不是 `run_live`
——纯粹因为 `run_live` 需要连一个真实的 Redis `stream:market:kline_ready`，没法脱离外部
服务独立跑。但这正好是设计文档 §5.6 `IPanelSource` 想证明的事：策略、`AlphaEngine`、
`LogSink` 这几行代码换到真实实盘时一个字都不用改，只需要把 `panel_source` 换成
`LivePanelSource(...)`——对比着看 examples/runner_backtest_with_stop_loss.py 就知道，两个
示例除了策略/sink 细节不一样，主循环的组装方式（`Runner(strategy, alpha_engine, sink)` +
`runner.run_backtest(panel_source)`）完全一致。

运行：
    python examples/paper_trading_log_sink.py
"""

from __future__ import annotations

import logging
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from sherpa.alpha.base import custom_alpha
from sherpa.alpha.engine import AlphaEngine
from sherpa.data.ch_reader import CHReader
from sherpa.data.panel_source import HistoricalPanelSource
from sherpa.data.universe import Universe
from sherpa.portfolio.weighting import top_k_long_short
from sherpa.strategy.base import BaseStrategy
from sherpa.strategy.runner import Runner
from sherpa.strategy.schema import TargetPosition
from sherpa.strategy.sink import LogSink

from _synthetic_market import FakeClickHouseClient, close_to_ch_long_df, make_synthetic_ohlcv

MOMENTUM_LOOKBACK = 60
ALPHA_NAME = f"custom.momentum_{MOMENTUM_LOOKBACK}"
TOP_K = 3


@custom_alpha(f"momentum_{MOMENTUM_LOOKBACK}", min_lookback=MOMENTUM_LOOKBACK + 1)
def momentum(panel):
    """过去 N 根的累计收益率，跟另外两个示例用的是同一个因子。"""
    return panel.close.pct_change(MOMENTUM_LOOKBACK)


class SimpleMomentumStrategy(BaseStrategy):
    """动量选股 + Top-K 多空，不带止损——这个示例的重点是 sink，不是策略状态。"""

    strategy_id = "paper_momentum"

    def on_bar(self, event, features) -> TargetPosition:
        weights = top_k_long_short(features[ALPHA_NAME], k=TOP_K)
        return TargetPosition({symbol: float(weight) for symbol, weight in weights.items()})


def main() -> None:
    # 打开 INFO 级日志、让 LogSink 的输出打到控制台——这是标准 logging 配置，不是 LogSink
    # 专属的东西，真实项目里通常在应用入口统一配一次。显式指到 stdout，跟下面的 print()
    # 共用一个流，输出顺序才不会因为 stdout/stderr 缓冲策略不同而错乱。
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)

    close, _mus = make_synthetic_ohlcv(n_symbols=10, n_bars=500, mu_spread=0.004, noise_std=0.01, seed=0)
    long_df = close_to_ch_long_df(close)

    ch_reader = CHReader(FakeClickHouseClient(long_df))
    universe = Universe(list(close.columns), ch_reader=ch_reader)
    # 只回放最后 5 根 bar，方便直接盯着控制台输出看——换成 LivePanelSource(...) 就是真实
    # 实盘链路，Runner/strategy/sink 这几行不用改一个字（见模块 docstring）。
    panel_source = HistoricalPanelSource(
        ch_reader,
        universe=universe,
        interval="1m",
        start_time=close.index[-5],
        end_time=close.index[-1],
        lookback_bars=MOMENTUM_LOOKBACK + 5,
    )

    alpha_engine = AlphaEngine([momentum()])
    runner = Runner(SimpleMomentumStrategy(), alpha_engine, LogSink())

    print("== 以下每一行都是 LogSink 落的日志：live_order_request，带确定性幂等 key ==\n")
    runner.run_backtest(panel_source)


if __name__ == "__main__":
    main()
