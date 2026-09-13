"""`BaseStrategy`：策略作者唯一需要继承的类（设计文档 §7）。

只负责纯策略逻辑（"这根 bar 我要什么仓位"），不接触 panel_source/sink 是回测还是实盘——
那是 `Runner` 的职责，`on_bar` 的签名和调用方式在两种驱动方式下完全一致。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import MarketEvent

from .schema import TargetPosition


class BaseStrategy:
    strategy_id: str = ""

    def __init__(self, **params):
        self.params = params
        if not self.strategy_id:
            self.strategy_id = type(self).__name__

    def setup(self) -> None:
        """`Runner` 开始跑主循环之前调用一次，默认空实现，按需覆写（加载参数/预热状态等）。"""

    def on_bar(self, event: MarketEvent, features: pd.DataFrame) -> TargetPosition:
        """`features`：`AlphaEngine.compute(event.panel)` 的输出，index=symbol，columns=alpha 名。"""
        raise NotImplementedError
