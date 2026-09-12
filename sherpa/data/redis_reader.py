"""Redis 的无状态 I/O 封装（设计文档 5.5）。

只负责发命令、拿回原始结构（数组/Hash/Stream条目），不做任何到 BarPanel 的转换。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional, Protocol, Sequence

KLINE_READY_STREAM = "stream:market:kline_ready"


class RedisClient(Protocol):
    """redis.Redis(..., decode_responses=True) 需要满足的最小接口，便于测试时注入假客户端。"""

    def pipeline(self): ...
    def hgetall(self, key: str) -> dict: ...
    def xread(self, streams: dict, block: Optional[int] = None, count: Optional[int] = None): ...


@dataclass(frozen=True)
class KlineReadyEvent:
    """stream:market:kline_ready 里的一条通知（设计文档 5.4）。"""

    entry_id: str
    interval: str
    timestamp_ms: int
    symbols_count: int


class RedisReader:
    def __init__(self, client: RedisClient):
        self._client = client

    def get_closed_window(self, symbols: Sequence[str], *, count: int = 200) -> dict[str, list[list]]:
        """批量拉取多个 symbol 的 kline:{SYM}:1m 已收盘滑窗，一次 pipeline 往返（上游 guide §3）。"""
        symbols = list(symbols)
        pipe = self._client.pipeline()
        for sym in symbols:
            pipe.lrange(f"kline:{sym}:1m", 0, count - 1)
        raw = pipe.execute()
        return {sym: [json.loads(item) for item in bars] for sym, bars in zip(symbols, raw)}

    def get_latest_closed_bars(self, symbols: Sequence[str]) -> dict[str, Optional[list]]:
        """批量拉取每个 symbol 最新的一根已收盘 bar（1m kline_ready 增量 append 用，见设计文档 5.5）。"""
        symbols = list(symbols)
        pipe = self._client.pipeline()
        for sym in symbols:
            pipe.lrange(f"kline:{sym}:1m", 0, 0)
        raw = pipe.execute()
        result: dict[str, Optional[list]] = {}
        for sym, bars in zip(symbols, raw):
            result[sym] = json.loads(bars[0]) if bars else None
        return result

    def get_livebar(self, symbol: str) -> Optional[dict[str, str]]:
        """未收盘当前 bar 的快照，供盯盘/止损类策略读取（上游 guide §2）。"""
        data = self._client.hgetall(f"livebar:{symbol}:1m")
        return data or None

    def read_kline_ready(
        self,
        *,
        last_id: str = "$",
        block_ms: Optional[int] = 0,
        count: int = 10,
    ) -> list[KlineReadyEvent]:
        """从 stream:market:kline_ready 读取新通知（上游 guide §4）。

        `last_id="$"` 表示只读之后的新事件；重放已有事件传 "0" 或具体 entry_id。
        """
        resp = self._client.xread({KLINE_READY_STREAM: last_id}, block=block_ms, count=count)
        events: list[KlineReadyEvent] = []
        for _stream_name, entries in resp:
            for entry_id, fields in entries:
                events.append(
                    KlineReadyEvent(
                        entry_id=entry_id,
                        interval=fields["interval"],
                        timestamp_ms=int(fields["timestamp"]),
                        symbols_count=int(fields["symbols_count"]),
                    )
                )
        return events
