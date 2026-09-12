"""测试用的假 ClickHouse / Redis 客户端，不依赖真实网络连接。

只实现 sherpa.data.ch_reader.ClickHouseClient / sherpa.data.redis_reader.RedisClient
两个 Protocol 要求的最小接口。
"""

from __future__ import annotations

import pandas as pd


class FakeCHClient:
    """记录收到的 SQL，按顺序把预先准备好的 DataFrame 吐出去（或用回调按 SQL 现算）。"""

    def __init__(self, responses=None, responder=None):
        self._responses = list(responses) if responses is not None else None
        self._responder = responder
        self.queries: list[str] = []

    def query_df(self, sql: str) -> pd.DataFrame:
        self.queries.append(sql)
        if self._responder is not None:
            return self._responder(sql)
        return self._responses.pop(0)


class _FakePipeline:
    def __init__(self, client: "FakeRedisClient"):
        self._client = client
        self._ops: list[tuple] = []

    def lrange(self, key, start, end):
        self._ops.append(("lrange", key, start, end))
        return self

    def hgetall(self, key):
        self._ops.append(("hgetall", key))
        return self

    def execute(self):
        results = []
        for op in self._ops:
            if op[0] == "lrange":
                _, key, start, end = op
                lst = self._client.lists.get(key, [])
                results.append(lst[start:] if end == -1 else lst[start : end + 1])
            elif op[0] == "hgetall":
                _, key = op
                results.append(dict(self._client.hashes.get(key, {})))
        self._ops = []
        return results


class FakeRedisClient:
    """支持 pipeline(lrange/hgetall) + 直接 hgetall + 一个可预先灌入条目的 kline_ready stream。"""

    def __init__(self):
        self.lists: dict[str, list] = {}
        self.hashes: dict[str, dict] = {}
        self._stream_entries: list[tuple[str, dict]] = []
        self._stream_pos = 0

    def pipeline(self):
        return _FakePipeline(self)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def lrange(self, key, start, end):
        lst = self.lists.get(key, [])
        return lst[start:] if end == -1 else lst[start : end + 1]

    def push_kline_ready(self, *, interval: str, timestamp_ms: int, symbols_count: int) -> None:
        entry_id = str(len(self._stream_entries))
        self._stream_entries.append(
            (
                entry_id,
                {
                    "interval": interval,
                    "timestamp": str(timestamp_ms),
                    "symbols_count": str(symbols_count),
                },
            )
        )

    def xread(self, streams, block=None, count=None):
        ((stream_name, _last_id),) = streams.items()
        if self._stream_pos >= len(self._stream_entries):
            return []
        n = count or 1
        batch = self._stream_entries[self._stream_pos : self._stream_pos + n]
        self._stream_pos += len(batch)
        return [(stream_name, batch)] if batch else []
