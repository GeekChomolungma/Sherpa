"""测试用的假 panel_source / sink，不依赖真实 CH/Redis 或 IPanelSource 的具体实现。"""

from __future__ import annotations

from typing import Iterator, Sequence

from sherpa.data.schema import MarketEvent
from sherpa.strategy.schema import SignalIntent


class FakePanelSource:
    """按构造时给定的顺序原样 yield 一串 MarketEvent，只实现 IPanelSource 协议的最小面。"""

    def __init__(self, events: Sequence[MarketEvent], symbols: Sequence[str]):
        self._events = list(events)
        self._symbols = list(symbols)

    def universe(self, as_of=None) -> list[str]:
        return list(self._symbols)

    def __iter__(self) -> Iterator[MarketEvent]:
        return iter(self._events)


class RecordingSink:
    """把收到的 intents 原样存进内存列表，用于断言 Runner 主循环的输出。"""

    def __init__(self):
        self.received: list[SignalIntent] = []
        self.submit_calls: int = 0

    def submit(self, intents: Sequence[SignalIntent]) -> None:
        self.submit_calls += 1
        self.received.extend(intents)
