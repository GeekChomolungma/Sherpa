"""ClickHouse 的无状态 I/O 封装（设计文档 5.5）。

只负责发查询、拿回长表 DataFrame，不做任何到 BarPanel 的转换——转换是
sherpa.data.normalizer 的职责，保持"指标层不接触网络连接"的硬性原则（设计文档 5.1）。
"""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

import pandas as pd

from .normalizer import CH_LONG_FORM_COLUMNS
from .schema import VALID_INTERVALS

# rollup 表 fapi_oi_* / fapi_ls_ratio_*（15m/1h/4h/1d）一个完整桶应该聚合到的 5m 样本数（guide §1b：
# "Filter on it — the newest bucket is normally incomplete"）。fetch_oi_history / fetch_ls_ratio_history 用它
# 把还没收满的最新一桶过滤成 NaN，而不是悄悄拿一个偏小的部分值当完整值用。
_ROLLUP_FULL_SAMPLES: dict[str, int] = {"15m": 3, "1h": 12, "4h": 48, "1d": 288}


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

    def has_open_interest(self) -> bool:
        """探测这套可选的 OI 模块是否开启（上游 guide §1b：先 `EXISTS TABLE` 再查，不要假设表存在）。"""
        return self._table_exists("fapi_oi_5m")

    def has_long_short_ratio(self) -> bool:
        """探测可选的多空比模块（`fapi_ls_ratio_*`）是否开启，同 `has_open_interest`。"""
        return self._table_exists("fapi_ls_ratio_5m")

    def _table_exists(self, name: str) -> bool:
        df = self._client.query_df(f"EXISTS TABLE {self._database}.{name}")
        if df.empty:
            return False
        return bool(int(str(df.iloc[0, 0])))

    def fetch_oi_history(
        self,
        symbols: Sequence[str],
        interval: str,
        *,
        start_time=None,
        end_time=None,
        lookback_bars: int | None = None,
    ) -> pd.DataFrame:
        """拉取一段 OI 长表，列名统一成 `symbol, start_time, open_interest[, open_interest_high, open_interest_low]`。

        跟 `fetch_history` 是同一套查询形状（FINAL、`LIMIT n BY symbol` 或区间过滤），但源表结构
        因 interval 而异，这里统一屏蔽掉（上游 guide §1b）：

        - `interval="1m"`：没有 `fapi_oi_1m`（OI 最细只到 5m），直接返回空表，不发查询——
          调用方（normalizer）据此让 `BarPanel.open_interest` 保持 `None`，不是报错。
        - `interval="5m"`：查原始表 `fapi_oi_5m` 的 `sum_open_interest`，没有高低两个字段。
        - 其余（15m/1h/4h/1d）：查 rollup 表的 `sum_open_interest_close/_high/_low`，并且
          `samples = 完整值`过滤掉还没收满的最新一桶——不然会把一个偏小的部分值当完整值用，
          这是 guide 里专门强调的"the newest bucket is normally incomplete"。
        """
        return self._fetch_optional_history(
            "fapi_oi",
            {"sum_open_interest": "open_interest"},
            symbols,
            interval,
            start_time=start_time,
            end_time=end_time,
            lookback_bars=lookback_bars,
        )

    def fetch_ls_ratio_history(
        self,
        symbols: Sequence[str],
        interval: str,
        *,
        start_time=None,
        end_time=None,
        lookback_bars: int | None = None,
    ) -> pd.DataFrame:
        """拉取一段多空比长表（`fapi_ls_ratio_*`），列名换成 `sherpa.data.schema.OPTIONAL_LS_RATIO_FIELDS` 的语义名：
        `symbol, start_time, long_short_ratio, top_account_long_short_ratio, top_position_long_short_ratio`，
        rollup 周期再加各自的 `_high/_low`。

        表结构、时间语义跟 OI 完全一样，所以 interval 的处理也一样（见 `fetch_oi_history`）：1m 不查、5m 查原始表、
        15m 及以上查 rollup 并按 `samples` 过滤没收满的桶。多空比列在库里是 Nullable，缺的值如实是 NaN。
        """
        return self._fetch_optional_history(
            "fapi_ls_ratio",
            {
                "count_long_short_ratio": "long_short_ratio",
                "count_toptrader_long_short_ratio": "top_account_long_short_ratio",
                "sum_toptrader_long_short_ratio": "top_position_long_short_ratio",
            },
            symbols,
            interval,
            start_time=start_time,
            end_time=end_time,
            lookback_bars=lookback_bars,
        )

    def _fetch_optional_history(
        self,
        table_prefix: str,
        columns: Mapping[str, str],
        symbols: Sequence[str],
        interval: str,
        *,
        start_time=None,
        end_time=None,
        lookback_bars: int | None = None,
    ) -> pd.DataFrame:
        """OI / 多空比这类"5m 原始表 + 15m 以上 rollup"可选数据的共用查询。`columns` 是 {库里列名: 输出列名}：
        5m 原始表直接取这个列；rollup 表取 `<列名>_close/_high/_low`，输出为 `<输出列名>/_high/_low`。"""
        empty_columns = ["symbol", "start_time", *columns.values()]
        if not symbols:
            return pd.DataFrame(columns=empty_columns)
        if interval not in VALID_INTERVALS:
            raise ValueError(f"unknown interval {interval!r}, expected one of {VALID_INTERVALS}")
        if lookback_bars is None and (start_time is None or end_time is None):
            raise ValueError("must provide either lookback_bars or both start_time and end_time")
        if interval == "1m":
            return pd.DataFrame(columns=empty_columns)

        table = f"{self._database}.{table_prefix}_{interval}"
        symbol_list = ", ".join(f"'{_escape(s)}'" for s in symbols)

        if interval == "5m":
            selected = [f"{src} AS {dst}" for src, dst in columns.items()]
            extra_where = ""
        else:
            selected = [
                f"{src}_{part} AS {dst}{suffix}"
                for src, dst in columns.items()
                for part, suffix in (("close", ""), ("high", "_high"), ("low", "_low"))
            ]
            extra_where = f" AND samples = {_ROLLUP_FULL_SAMPLES[interval]}"
        columns_sql = ", ".join(["symbol", "start_time", *selected])

        if lookback_bars is not None:
            sql = (
                f"SELECT {columns_sql} FROM {table} FINAL "
                f"WHERE symbol IN ({symbol_list}){extra_where} "
                f"ORDER BY symbol, start_time DESC "
                f"LIMIT {int(lookback_bars)} BY symbol"
            )
        else:
            sql = (
                f"SELECT {columns_sql} FROM {table} FINAL "
                f"WHERE symbol IN ({symbol_list}) "
                f"AND start_time >= '{_format_ts(start_time)}' "
                f"AND start_time <= '{_format_ts(end_time)}'"
                f"{extra_where} "
                f"ORDER BY symbol, start_time"
            )

        df = self._client.query_df(sql)
        if df.empty:
            return df
        return df.sort_values("start_time").reset_index(drop=True)


def _escape(value: str) -> str:
    return value.replace("'", "''")


def _format_ts(value) -> str:
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")
