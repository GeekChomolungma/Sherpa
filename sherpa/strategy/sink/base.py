"""`ISignalReceiver`：Sherpa 和下游 Webhooker 之间的唯一接口（设计文档 §9）。

本仓库只负责生成信号，不负责下单/撮合/资金清算——这些是 Webhooker 的职责。三个具体实现
（`LogSink`/`BacktestSink`/`WebhookSink`）各自一个文件，互不感知彼此的存在，只共享这一个协议。
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from ..schema import SignalIntent


@runtime_checkable
class ISignalReceiver(Protocol):
    def submit(self, intents: Sequence[SignalIntent]) -> None: ...
