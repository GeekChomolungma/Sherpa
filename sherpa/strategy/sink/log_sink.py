"""`LogSink`：paper trading 的默认实现（设计文档 §9.1）。

只落日志，不发网络请求——调用 `sherpa.live.build_live_requests` 把收到的 `SignalIntent`
转成 `LiveOrderRequest` 再落日志，日志里看到的是"如果这时候接的是 `WebhookSink`，真正会
派发出去的样子"（幂等 key、派发时刻都在），不是简单转发 `Runner` 的原始输出——这也是它
能被当作 paper trading 默认实现来用的原因。在 `WebhookSink` 就绪前，Sherpa 的实时链路
可以先用它验证信号是否符合预期。
"""

from __future__ import annotations

import logging
from typing import Sequence

from sherpa.live.request import SignalIntentLike, build_live_requests

logger = logging.getLogger(__name__)


class LogSink:
    def __init__(self, *, logger_: logging.Logger | None = None):
        self._logger = logger_ or logger

    def submit(self, intents: Sequence[SignalIntentLike]) -> None:
        for request in build_live_requests(intents):
            self._logger.info("live_order_request %s", request)
