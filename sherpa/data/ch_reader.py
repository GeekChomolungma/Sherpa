"""ClickHouse 的无状态 I/O 封装（设计文档 5.5）。

只负责发查询、拿回长表 DataFrame，不做任何到 BarPanel 的转换——转换是
sherpa.data.normalizer 的职责，保持"指标层不接触网络连接"的硬性原则（设计文档 5.1）。
"""

from __future__ import annotations

from typing import Protocol, Sequence

import pandas as pd

from .normalizer import CH_LONG_FORM_COLUMNS
from .schema import VALID_INTERVALS


class ClickHouseClient(Protocol):
    """clickhouse_connect.get_client(...) 返回对象需要满足的最小接口，便于测试时注入假客户端。"""

    def query_df(self, sql: str) -> pd.DataFrame: ...


class CHReader:
    def __init__(self, client: ClickHouseClient, *, database: str = "market"):
        self._client = client
        self._database = database

    def _table(self, interval: str) -> str:
        if interval not in VALID_INTERVALS:
            raise ValueError(f"unknown interval {interval!r}, expected one of {VALID_INTERVALS}")
        return f"{self._database}.fapi_kline_{interval}"

    def fetch_history(
        self,
        symbols: Sequence[str],
        interval: str,
        *,
        start_time=None,
        end_time=None,
        lookback_bars: int | None = None,
    ) -> pd.DataFrame:
        """拉取一段长表数据，永远带 FINAL（防止 ReplacingMergeTree 未合并重复，见上游 guide）。

        要么给 (start_time, end_time) 拉一个区间，要么给 lookback_bars 拉每个 symbol 最新的 N 根
        （用 ClickHouse 的 `LIMIT n BY symbol`，一次查询搞定，不需要逐 symbol 查）。
        """
        if not symbols:
            return pd.DataFrame(columns=CH_LONG_FORM_COLUMNS)
        if lookback_bars is None and (start_time is None or end_time is None):
            raise ValueError("must provide either lookback_bars or both start_time and end_time")

        table = self._table(interval)
        symbol_list = ", ".join(f"'{_escape(s)}'" for s in symbols)
        columns = ", ".join(CH_LONG_FORM_COLUMNS)

        if lookback_bars is not None:
            sql = (
                f"SELECT {columns} FROM {table} FINAL "
                f"WHERE symbol IN ({symbol_list}) "
                f"ORDER BY symbol, start_time DESC "
                f"LIMIT {int(lookback_bars)} BY symbol"
            )
        else:
            sql = (
                f"SELECT {columns} FROM {table} FINAL "
                f"WHERE symbol IN ({symbol_list}) "
                f"AND start_time >= '{_format_ts(start_time)}' "
                f"AND start_time <= '{_format_ts(end_time)}' "
                f"ORDER BY symbol, start_time"
            )

        df = self._client.query_df(sql)
        if df.empty:
            return df
        return df.sort_values("start_time").reset_index(drop=True)

    def get_all_symbols(self) -> list[str]:
        sql = f"SELECT DISTINCT symbol FROM {self._database}.fapi_kline_1m FINAL ORDER BY symbol"
        df = self._client.query_df(sql)
        return df["symbol"].tolist()

    def get_listing_times(self) -> dict[str, pd.Timestamp]:
        """每个 symbol 最早出现的 1m bar 的 start_time —— point-in-time universe 用（设计文档 5.3）。

        ClickHouse 没有专门记录"上线时间"的字段，只能用 min(start_time) 倒推；这是一次全表
        GROUP BY，调用方（Universe）应该缓存结果，不要每次构造 BarPanel 都查一遍。
        """
        sql = (
            f"SELECT symbol, min(start_time) AS listed_at "
            f"FROM {self._database}.fapi_kline_1m FINAL GROUP BY symbol"
        )
        df = self._client.query_df(sql)
        if df.empty:
            return {}
        listed_at = pd.to_datetime(df["listed_at"], utc=True)
        return dict(zip(df["symbol"], listed_at))


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _format_ts(value) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
