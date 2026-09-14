"""`BacktestSink`：事件驱动回测的 sink，只是 `sherpa.backtest.event_driven.Simulator` 的
薄转发层（设计文档 §8.4.3/§9.2）——不自己维护任何持仓/成本状态，真正的换手/成本/净值计算
全部在 `sherpa.backtest` 里完成。`strategy` 包依赖 `backtest`，反过来不允许。
"""

from __future__ import annotations

from typing import Sequence

from sherpa.backtest.event_driven import Simulator

from ..schema import SignalIntent


class BacktestSink:
    def __init__(self, simulator: Simulator):
        self._simulator = simulator

    def submit(self, intents: Sequence[SignalIntent]) -> None:
        self._simulator.on_intents(intents)
