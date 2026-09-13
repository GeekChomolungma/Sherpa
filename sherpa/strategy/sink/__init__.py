"""下游对接子模块（设计文档 §9）：`ISignalReceiver` 协议 + 三个具体实现。

每种驱动方式一个文件，互相独立演进：
- `log_sink.LogSink`：实盘链路打通阶段的过渡桩，v1 唯一可用的实现。
- `backtest_sink.BacktestSink`：依赖第8章撮合引擎，占位报错。
- `webhook_sink.WebhookSink`：依赖下游 Webhooker，占位报错。
"""

from __future__ import annotations

from .backtest_sink import BacktestSink
from .base import ISignalReceiver
from .log_sink import LogSink
from .webhook_sink import WebhookSink

__all__ = ["ISignalReceiver", "LogSink", "BacktestSink", "WebhookSink"]
