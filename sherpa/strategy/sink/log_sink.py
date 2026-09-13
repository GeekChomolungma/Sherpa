"""`LogSink`：实盘链路打通阶段的过渡桩（设计文档 §9）。

只落日志，不发网络请求——在 Webhooker 就绪前，Sherpa 的实时链路可以先用它验证信号是否
符合预期。是三个 sink 实现里唯一在 v1 范围内真正可用的一个。
"""

from __future__ import annotations

import logging
from typing import Sequence

from ..schema import SignalIntent

logger = logging.getLogger(__name__)


class LogSink:
    def __init__(self, *, logger_: logging.Logger | None = None):
        self._logger = logger_ or logger

    def submit(self, intents: Sequence[SignalIntent]) -> None:
        for intent in intents:
            self._logger.info("signal_intent %s", intent)
