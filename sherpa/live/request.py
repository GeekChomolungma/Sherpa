"""`LiveOrderRequest`：把 `SignalIntent` 标准化成"准备派发"的形状（设计文档 §8.5.2）。

`LogSink`/`WebhookSink` 共用这一步——同一个 `build_live_requests`，一个用来落日志，一个
（将来）用来发 HTTP 请求，避免幂等 key/派发时间戳这类逻辑在两个 sink 里各写一份。

只做格式转换 + 补充幂等 key/派发时间戳，不改变 `target_percent` 等决策数字——会改变决策
结果的逻辑（比如仓位再平衡阈值）不属于这个模块的职责，讨论过后明确排除在外（见 §8.5.1）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence, runtime_checkable

import pandas as pd


@runtime_checkable
class SignalIntentLike(Protocol):
    """`build_live_requests` 需要的最小信号形状——结构类型，不 import `sherpa.strategy.SignalIntent`。

    跟 `sherpa.backtest.event_driven.TargetIntent` 同样的理由：`sherpa.live` 不反向依赖
    `sherpa.strategy`，真正的 `SignalIntent` 天然满足这个 Protocol，不需要做任何转换。
    """

    strategy_id: str
    symbol: str
    target_percent: float
    bar_end_time: pd.Timestamp
    generated_at: pd.Timestamp


@dataclass(frozen=True)
class LiveOrderRequest:
    """一条标准化的、可以直接拿去落日志或者发 HTTP 请求的实盘信号。"""

    idempotency_key: str
    strategy_id: str
    symbol: str
    target_percent: float
    bar_end_time: pd.Timestamp
    generated_at: pd.Timestamp
    dispatched_at: pd.Timestamp


def build_idempotency_key(*, strategy_id: str, symbol: str, bar_end_time: pd.Timestamp) -> str:
    """确定性 key：同一个策略对同一根 bar 的同一个 symbol 做出的决策，无论重放/重试多少次，
    算出来的 key 都一样——不像 `SignalIntent.event_id`，那是 `Runner` 每次都新生成的随机
    UUID，进程重启后就变了，没法用来判断"这条信号是不是已经处理过"。
    """
    return f"{strategy_id}:{bar_end_time.isoformat()}:{symbol}"


def build_live_requests(intents: Sequence[SignalIntentLike]) -> list[LiveOrderRequest]:
    """把一批 `SignalIntent` 转成 `LiveOrderRequest`，同一批共享同一个 `dispatched_at`
    （它们是同一次 `on_bar` 产出、同一次 `submit()` 调用一起处理的）。
    """
    dispatched_at = pd.Timestamp.now(tz="UTC")
    return [
        LiveOrderRequest(
            idempotency_key=build_idempotency_key(
                strategy_id=intent.strategy_id, symbol=intent.symbol, bar_end_time=intent.bar_end_time
            ),
            strategy_id=intent.strategy_id,
            symbol=intent.symbol,
            target_percent=intent.target_percent,
            bar_end_time=intent.bar_end_time,
            generated_at=intent.generated_at,
            dispatched_at=dispatched_at,
        )
        for intent in intents
    ]
