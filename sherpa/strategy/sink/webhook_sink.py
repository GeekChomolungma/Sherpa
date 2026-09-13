"""`WebhookSink`：实盘用 sink，把 `SignalIntent` 发给下游 Webhooker（设计文档 §9）。

尚未实现——留给 Webhooker（下单/撮合/仓位对齐，超出本仓库范围）就绪之后再做，本设计不
展开其重试/幂等/签名细节，届时再回来补。在那之前，实时链路先用 `LogSink` 观察信号。
"""

from __future__ import annotations

from typing import Sequence

from ..schema import SignalIntent


class WebhookSink:
    def submit(self, intents: Sequence[SignalIntent]) -> None:
        raise NotImplementedError("WebhookSink 等下游 Webhooker 就绪后再实现（设计文档 §9）")
