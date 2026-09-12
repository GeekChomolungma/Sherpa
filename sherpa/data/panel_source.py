"""统一驱动接口：回测回放 与 实盘监听 共用同一套迭代协议（设计文档 5.6）。

Pipeline 层的主循环因此不需要关心自己是在回测还是实盘：

    for event in panel_source:
        features = alpha_engine.compute(event.panel)
        intents = strategy.on_bar(event, features)
        sink.submit(intents)
"""

from __future__ import annotations

from typing import Iterator, Optional, Protocol, Sequence, runtime_checkable

import pandas as pd

from .ch_reader import CHReader
from .normalizer import ch_long_to_panel
from .redis_reader import RedisReader
from .schema import MarketEvent, interval_to_timedelta
from .universe import Universe
from .window_cache import WindowCache


@runtime_checkable
class IPanelSource(Protocol):
    def universe(self, as_of: Optional[pd.Timestamp] = None) -> list[str]: ...

    def __iter__(self) -> Iterator[MarketEvent]: ...


class HistoricalPanelSource:
    """回测用数据源：一次性拉好区间数据，按 bar 顺序逐个 yield MarketEvent。

    防前视偏差（设计文档 5.6）：
    - 第一道保险：每个 event.panel 只截取到 event.bar_end_time 为止的数据，通过按位置切片
      （而不是先构造完整未来数据再"假装"截断）实现——slice 本身不接触之后的行。
    - 第二道保险在回测引擎（撮合层），不在本模块职责范围内。
    """

    def __init__(
        self,
        ch_reader: CHReader,
        *,
        universe: Universe,
        interval: str,
        start_time,
        end_time,
        lookback_bars: int = 200,
    ):
        self._ch_reader = ch_reader
        self._universe = universe
        self._interval = interval
        self._start_time = _to_utc(start_time)
        self._end_time = _to_utc(end_time)
        self._lookback_bars = lookback_bars

    def universe(self, as_of: Optional[pd.Timestamp] = None) -> list[str]:
        return self._universe.as_of(self._end_time if as_of is None else as_of)

    def __iter__(self) -> Iterator[MarketEvent]:
        symbols = self.universe()
        if not symbols:
            return

        # 往前多拉 lookback_bars 根做 padding，这样区间刚开始的几个 event 也能拿到完整窗口，
        # 而不是从空窗口慢慢"攒"起来。
        padded_start = self._start_time - interval_to_timedelta(self._interval) * self._lookback_bars
        long_df = self._ch_reader.fetch_history(
            symbols, self._interval, start_time=padded_start, end_time=self._end_time
        )
        full_panel = ch_long_to_panel(long_df, interval=self._interval, symbols=symbols)

        for pos, ts in enumerate(full_panel.index):
            if ts < self._start_time:
                continue
            lo = max(0, pos - self._lookback_bars + 1)
            window = full_panel.slice(slice(lo, pos + 1))
            symbols_count = int(window.close.iloc[-1].notna().sum())
            yield MarketEvent.build(
                interval=self._interval,
                bar_start_time=ts,
                symbols_count=symbols_count,
                universe_size=len(symbols),
                panel=window,
            )


class LivePanelSource:
    """实盘数据源：阻塞监听 stream:market:kline_ready。

    v0.2 决策（设计文档 5.5/5.7）：
    - interval="1m" 走内部持有的 WindowCache（有状态，增量 append）。
    - 粗周期（5m/15m/1h/4h/1d）每次现查 ClickHouse 的完整 lookback，不做常驻缓存；
      coverage_ratio/symbols_count 用查询结果重新计算，不采信通知里"借来的"symbols_count。
    """

    def __init__(
        self,
        ch_reader: CHReader,
        redis_reader: RedisReader,
        *,
        universe: Universe,
        intervals: Sequence[str],
        window_size: int = 200,
        lookback_bars: int = 200,
        block_ms: int = 5000,
        read_count: int = 10,
    ):
        self._ch_reader = ch_reader
        self._redis_reader = redis_reader
        self._universe = universe
        self._intervals = set(intervals)
        self._lookback_bars = lookback_bars
        self._block_ms = block_ms
        self._read_count = read_count
        self._window_cache: Optional[WindowCache] = None
        if "1m" in self._intervals:
            self._window_cache = WindowCache(
                redis_reader, universe=universe.all_symbols(), window_size=window_size
            )

    def universe(self, as_of: Optional[pd.Timestamp] = None) -> list[str]:
        return self._universe.all_symbols()

    def __iter__(self) -> Iterator[MarketEvent]:
        last_id = "$"
        while True:
            events = self._redis_reader.read_kline_ready(
                last_id=last_id, block_ms=self._block_ms, count=self._read_count
            )
            for kr_event in events:
                last_id = kr_event.entry_id
                if kr_event.interval not in self._intervals:
                    continue
                if kr_event.interval == "1m":
                    assert self._window_cache is not None
                    yield self._window_cache.on_kline_ready(kr_event)
                else:
                    yield self._build_coarse_event(kr_event.interval, kr_event.timestamp_ms, kr_event.symbols_count)

    def _build_coarse_event(self, interval: str, timestamp_ms: int, notified_symbols_count: int) -> MarketEvent:
        symbols = self._universe.all_symbols()
        long_df = self._ch_reader.fetch_history(symbols, interval, lookback_bars=self._lookback_bars)
        panel = ch_long_to_panel(long_df, interval=interval, symbols=symbols)
        symbols_count = int(panel.close.iloc[-1].notna().sum()) if len(panel.index) else 0
        return MarketEvent.build(
            interval=interval,
            bar_start_time=pd.Timestamp(timestamp_ms, unit="ms", tz="UTC"),
            symbols_count=symbols_count,
            universe_size=len(symbols),
            panel=panel,
            schema_notes={
                "coverage_source": "recomputed_from_ch_query",
                "notified_symbols_count": notified_symbols_count,
            },
        )


def _to_utc(value) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")
