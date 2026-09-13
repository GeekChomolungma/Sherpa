"""策略编排层的信号契约（设计文档 §9）：`TargetPosition` / `SignalIntent`。

策略只产出 `TargetPosition`（纯业务语义的目标仓位）；把它标准化成携带 `event_id` /
`generated_at` 等元数据的 `SignalIntent` 是 Runner 的职责，不能让 `BaseStrategy` 自己去拼
这些字段——这样回测和实盘复用同一个 `on_bar` 时，策略代码不需要关心自己是被谁调用的。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pandas as pd


@dataclass(frozen=True)
class TargetPosition:
    """策略在一次 `on_bar` 里给出的目标仓位：symbol -> 目标仓位百分比。

    百分比可正可负（负数=做空），具体口径（是否杠杆、是否归一化）由策略自己定义，
    本层不做校验/裁剪——那是回测撮合/风控的职责，不是信号契约的职责。
    """

    weights: Mapping[str, float] = field(default_factory=dict)

    def items(self):
        return self.weights.items()


@dataclass(frozen=True)
class SignalIntent:
    """下游 `ISignalReceiver` 消费的标准化交易意图（设计文档 §9 最小字段集）。

    执行细节（下单类型、滑点容忍度等）留给下游 Webhooker，本层只负责"生成信号"。
    """

    event_id: str
    strategy_id: str
    symbol: str
    signal_type: str
    target_percent: float
    bar_end_time: pd.Timestamp
    generated_at: pd.Timestamp
