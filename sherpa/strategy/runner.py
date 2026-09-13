"""`Runner`：把 `IPanelSource` + `AlphaEngine` + `BaseStrategy` + `ISignalReceiver` 串成
设计文档 §5.6 的主循环。

`run_backtest`/`run_live` 只是语义化别名，实现体全部委托给同一个 `run()`——这是设计文档
反复强调的硬约束："同一套策略代码，两种驱动方式"，差异只应该体现在调用方注入的
`panel_source`/`sink` 具体类型上，不允许在这里为回测/实盘分叉出两份主循环逻辑。
"""

from __future__ import annotations

import uuid

import pandas as pd

from sherpa.alpha.engine import AlphaEngine
from sherpa.data.panel_source import IPanelSource
from sherpa.data.schema import MarketEvent

from .base import BaseStrategy
from .schema import SignalIntent, TargetPosition
from .sink import ISignalReceiver


class Runner:
    def __init__(self, strategy: BaseStrategy, alpha_engine: AlphaEngine, sink: ISignalReceiver):
        self._strategy = strategy
        self._alpha_engine = alpha_engine
        self._sink = sink

    def run(self, panel_source: IPanelSource) -> None:
        self._strategy.setup()
        for event in panel_source:
            features = self._alpha_engine.compute(event.panel)
            target = self._strategy.on_bar(event, features)
            intents = self._to_intents(event, target)
            if intents:
                self._sink.submit(intents)

    def run_backtest(self, panel_source: IPanelSource) -> None:
        """语义化别名：调用方明确表达"这是回测"，实现完全复用 `run()`（见模块 docstring）。"""
        self.run(panel_source)

    def run_live(self, panel_source: IPanelSource) -> None:
        """语义化别名：调用方明确表达"这是实盘"，实现完全复用 `run()`（见模块 docstring）。"""
        self.run(panel_source)

    def _to_intents(self, event: MarketEvent, target: TargetPosition | None) -> list[SignalIntent]:
        if not target:
            return []
        event_id = str(uuid.uuid4())
        generated_at = pd.Timestamp.now(tz="UTC")
        return [
            SignalIntent(
                event_id=event_id,
                strategy_id=self._strategy.strategy_id,
                symbol=symbol,
                signal_type="target_percent",
                target_percent=weight,
                bar_end_time=event.bar_end_time,
                generated_at=generated_at,
            )
            for symbol, weight in target.items()
        ]
