"""数据接入层 -> 指标层 数据契约。

对应设计文档 docs/SHERPA_DESIGN.md 第 5 章：`BarPanel` / `MarketEvent`。
指标/Alpha 层只允许依赖本模块定义的结构，不允许直接接触 ClickHouse/Redis 的原始格式。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

import pandas as pd

SCHEMA_VERSION = "1.0"

# 顺序即 dataclass 字段顺序 / Redis 紧凑数组字段顺序（去掉 start_time 之后）。
PANEL_FIELDS: tuple[str, ...] = (
    "open",
    "high",
    "low",
    "close",
    "volume",
    "quote_volume",
    "taker_buy_volume",
    "taker_buy_quote_volume",
    "trades_count",
)

# 可选字段：open interest。故意不放进 PANEL_FIELDS——PANEL_FIELDS 同时驱动 Redis
# kline:{SYM}:1m 紧凑数组的定长校验，而 OI 只存在于 ClickHouse 的 5m 及以上级别
# （fapi_oi_5m/15m/1h/4h/1d），1m/Redis 恒无此数据（见 docs/DATA_CONSUMER_GUIDE.md §1b）。
# 把它做成核心字段会强迫每一个 1m/Redis/合成测试场景都要"造一份不存在的 OI 数据"。
# `open_interest` 对齐的是 5m 原始表的 sum_open_interest 或 15m+ rollup 的
# sum_open_interest_close——跟该 interval 的 close 同一个信息可得时点，可以直接当
# 一张普通 (T, N) DataFrame 用，跟 panel.close 用法完全一样。
# `open_interest_high`/`_low` 只有 15m 及以上（rollup 表）才有，5m 原始表没有高低，
# 恒为 None。
OPTIONAL_OI_FIELDS: tuple[str, ...] = ("open_interest", "open_interest_high", "open_interest_low")

# 可选字段：多空比（`market.fapi_ls_ratio_*`），跟 OI 同一个上游模块、同一套表结构和时间语义——`start_time` 是
# K 线开盘时刻，值属于收盘时刻（5m 原始表 snap_time = start_time + 5m；rollup 的 `_close` 是桶内最后一个 5m 值），
# 所以跟 `close` 同一个信息可得时点。不放进 PANEL_FIELDS 的理由同 OI。字段名用语义名，跟库里列名的对应：
#   long_short_ratio               <- count_long_short_ratio            全市场账户多空比（多头账户数 / 空头账户数）
#   top_account_long_short_ratio   <- count_toptrader_long_short_ratio  大户账户多空比
#   top_position_long_short_ratio  <- sum_toptrader_long_short_ratio    大户持仓多空比（多头持仓量 / 空头持仓量）
# `_high`/`_low` 是桶内 5m 值的最高 / 最低，只有 15m 及以上（rollup 表）才有，5m 原始表恒为 None。
LS_RATIO_METRICS: tuple[str, ...] = (
    "long_short_ratio",
    "top_account_long_short_ratio",
    "top_position_long_short_ratio",
)
OPTIONAL_LS_RATIO_FIELDS: tuple[str, ...] = tuple(
    f"{metric}{suffix}" for metric in LS_RATIO_METRICS for suffix in ("", "_high", "_low")
)

# 全部可选字段：校验、切片都按这一份走，以后再加可选数据源只改这里
OPTIONAL_FIELDS: tuple[str, ...] = OPTIONAL_OI_FIELDS + OPTIONAL_LS_RATIO_FIELDS

VALID_INTERVALS: tuple[str, ...] = ("1m", "5m", "15m", "1h", "4h", "1d")

_INTERVAL_SECONDS: Mapping[str, int] = {
    "1m": 60,
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "4h": 4 * 60 * 60,
    "1d": 24 * 60 * 60,
}


def interval_to_timedelta(interval: str) -> pd.Timedelta:
    """把 "1m"/"5m"/... 换算成 pd.Timedelta，用于推导 bar_end_time（设计文档 5.4）。"""
    try:
        seconds = _INTERVAL_SECONDS[interval]
    except KeyError as exc:
        raise ValueError(f"unknown interval {interval!r}, expected one of {VALID_INTERVALS}") from exc
    return pd.Timedelta(seconds=seconds)


def _ensure_utc_timestamp(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


@dataclass(frozen=True)
class BarPanel:
    """多时间戳 x 多 symbol 的宽表容器：行 = start_time(UTC), 列 = symbol。

    指标/Alpha 层唯一直接消费的数据结构（设计文档 5.1、5.2）。
    """

    interval: str
    symbols: tuple[str, ...]

    open: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame
    close: pd.DataFrame
    volume: pd.DataFrame
    quote_volume: pd.DataFrame
    taker_buy_volume: pd.DataFrame
    taker_buy_quote_volume: pd.DataFrame
    trades_count: pd.DataFrame

    coverage: pd.Series

    # 可选 OI 字段，见 OPTIONAL_OI_FIELDS 上面的说明；默认 None 表示"这个 panel 没有 OI 数据"
    # ——可能是 interval=1m/Redis 来源（恒无），也可能是调用方没有请求（include_open_interest=False），
    # 也可能是该 symbol/时间段还没有回补到 OI（真实缺失，如实 NaN/None，不做任何填充）。
    open_interest: Optional[pd.DataFrame] = None
    open_interest_high: Optional[pd.DataFrame] = None
    open_interest_low: Optional[pd.DataFrame] = None

    # 可选多空比字段，见 OPTIONAL_LS_RATIO_FIELDS 上面的说明；None 的含义同 OI
    long_short_ratio: Optional[pd.DataFrame] = None
    long_short_ratio_high: Optional[pd.DataFrame] = None
    long_short_ratio_low: Optional[pd.DataFrame] = None
    top_account_long_short_ratio: Optional[pd.DataFrame] = None
    top_account_long_short_ratio_high: Optional[pd.DataFrame] = None
    top_account_long_short_ratio_low: Optional[pd.DataFrame] = None
    top_position_long_short_ratio: Optional[pd.DataFrame] = None
    top_position_long_short_ratio_high: Optional[pd.DataFrame] = None
    top_position_long_short_ratio_low: Optional[pd.DataFrame] = None

    schema_version: str = SCHEMA_VERSION
    schema_notes: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.interval not in VALID_INTERVALS:
            raise ValueError(f"unknown interval {self.interval!r}, expected one of {VALID_INTERVALS}")

        index = self.open.index
        if not isinstance(index, pd.DatetimeIndex):
            raise TypeError("BarPanel index must be a pandas.DatetimeIndex")
        if index.tz is None:
            raise ValueError("BarPanel index must be tz-aware UTC")
        if not index.is_monotonic_increasing:
            raise ValueError("BarPanel index must be sorted ascending")
        if index.has_duplicates:
            raise ValueError("BarPanel index must not contain duplicate timestamps")

        expected_columns = pd.Index(self.symbols)
        for name in PANEL_FIELDS:
            frame = getattr(self, name)
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"BarPanel.{name} must be a pandas.DataFrame")
            if not frame.index.equals(index):
                raise ValueError(f"BarPanel.{name} index does not match BarPanel.open index")
            if not frame.columns.equals(expected_columns):
                raise ValueError(f"BarPanel.{name} columns do not match BarPanel.symbols")

        if not self.coverage.index.equals(index):
            raise ValueError("BarPanel.coverage index does not match BarPanel.open index")

        for name in OPTIONAL_FIELDS:
            frame = getattr(self, name)
            if frame is None:
                continue  # 允许缺席：1m/Redis 来源恒无，或调用方没有请求 OI / 多空比
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"BarPanel.{name} must be a pandas.DataFrame or None")
            if not frame.index.equals(index):
                raise ValueError(f"BarPanel.{name} index does not match BarPanel.open index")
            if not frame.columns.equals(expected_columns):
                raise ValueError(f"BarPanel.{name} columns do not match BarPanel.symbols")

    @property
    def has_open_interest(self) -> bool:
        """这个 panel 是否带了 OI 数据——1m/Redis 来源、或调用方没请求时恒为 False。"""
        return self.open_interest is not None

    @property
    def has_long_short_ratio(self) -> bool:
        """这个 panel 是否带了多空比数据（至少有全市场账户多空比）。"""
        return self.long_short_ratio is not None

    def field(self, name: str) -> pd.DataFrame:
        if name not in PANEL_FIELDS:
            raise KeyError(f"unknown BarPanel field {name!r}, expected one of {PANEL_FIELDS}")
        return getattr(self, name)

    def tail(self, n: int) -> "BarPanel":
        """取最近 n 根，构造一个新的 BarPanel（用于滚动窗口 evict / 回测窗口截断）。"""
        return self.slice(slice(-n, None))

    def loc_until(self, t: pd.Timestamp) -> "BarPanel":
        """只保留 index <= t 的行——回测防前视偏差的核心工具（设计文档 5.6）。"""
        t = _ensure_utc_timestamp(t)
        mask = self.open.index <= t
        return self.slice(mask)

    def slice(self, selector) -> "BarPanel":
        """按位置切片/布尔掩码取子集（不是按 label），selector 直接转给 `.iloc[]`。

        可选字段（OI、多空比）：为 None 时保持 None（不会凭空切出一张空表），非 None 时跟核心字段
        同步切片，保证切片前后它们的 index 始终和 open/close 对齐。
        """
        kwargs = {name: getattr(self, name).iloc[selector] for name in PANEL_FIELDS}
        for name in OPTIONAL_FIELDS:
            frame = getattr(self, name)
            kwargs[name] = frame.iloc[selector] if frame is not None else None

        return BarPanel(
            interval=self.interval,
            symbols=self.symbols,
            coverage=self.coverage.iloc[selector],
            schema_version=self.schema_version,
            schema_notes=dict(self.schema_notes),
            **kwargs,
        )

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.open.index


def build_coverage(reference_field: pd.DataFrame, universe_size: int) -> pd.Series:
    """按"非缺失 symbol 数 / universe 总数"计算逐行覆盖率（设计文档 5.2 coverage 字段）。"""
    if universe_size <= 0:
        return pd.Series(0.0, index=reference_field.index, name="coverage")
    counts = reference_field.notna().sum(axis=1)
    return (counts / universe_size).rename("coverage")


@dataclass(frozen=True)
class MarketEvent:
    """一次「截面就绪」事件的信封（设计文档 5.4）。"""

    interval: str
    bar_start_time: pd.Timestamp
    bar_end_time: pd.Timestamp
    symbols_count: int
    coverage_ratio: float
    panel: BarPanel
    is_cold_start: bool = False
    schema_notes: dict = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        *,
        interval: str,
        bar_start_time,
        symbols_count: int,
        universe_size: int,
        panel: BarPanel,
        is_cold_start: bool = False,
        schema_notes: dict | None = None,
    ) -> "MarketEvent":
        """构造 MarketEvent，`bar_end_time` 按设计文档 5.4 自行推导（不依赖上游 end_time 字段）。

        对齐 Binance kline 的 close_time 惯例：close_time = open_time + duration - 1ms
        （比如 1m bar 是 [10:00:00.000, 10:00:59.999]），所以这里要减掉 1 毫秒，
        不能直接等于下一根的 start_time，否则和上游 ClickHouse `end_time` 字段会系统性差 1ms。
        """
        start = _ensure_utc_timestamp(bar_start_time)
        end = start + interval_to_timedelta(interval) - pd.Timedelta(milliseconds=1)
        coverage_ratio = (symbols_count / universe_size) if universe_size > 0 else 0.0
        return cls(
            interval=interval,
            bar_start_time=start,
            bar_end_time=end,
            symbols_count=symbols_count,
            coverage_ratio=coverage_ratio,
            panel=panel,
            is_cold_start=is_cold_start,
            schema_notes=dict(schema_notes or {}),
        )


def empty_panel(interval: str, symbols: Sequence[str]) -> BarPanel:
    """空面板，用于占位/测试。"""
    symbols = tuple(symbols)
    index = pd.DatetimeIndex([], tz="UTC", name="start_time")
    columns = pd.Index(symbols)
    frames = {name: pd.DataFrame(index=index, columns=columns, dtype="float64") for name in PANEL_FIELDS}
    coverage = pd.Series(dtype="float64", index=index, name="coverage")
    return BarPanel(interval=interval, symbols=symbols, coverage=coverage, **frames)
