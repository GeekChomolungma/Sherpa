import json

import pandas as pd

from sherpa.data.ch_reader import CHReader
from sherpa.data.panel_source import HistoricalPanelSource, LivePanelSource
from sherpa.data.redis_reader import RedisReader

from .fakes import FakeCHClient, FakeRedisClient


class _FakeUniverse:
    """满足 panel_source 期望的 .as_of()/.all_symbols() 接口的最小 stub，不牵扯 CHReader.get_listing_times。"""

    def __init__(self, symbols):
        self._symbols = list(symbols)

    def as_of(self, t):
        return list(self._symbols)

    def all_symbols(self):
        return list(self._symbols)


def _ch_row(symbol, start_time, value):
    return {
        "symbol": symbol,
        "start_time": start_time,
        "open": value,
        "high": value + 1,
        "low": value - 1,
        "close": value,
        "volume": value * 10,
        "quote_volume": value * 100,
        "taker_buy_volume": value * 5,
        "taker_buy_quote_volume": value * 50,
        "trades_count": 1,
    }


def test_historical_panel_source_sliding_window_no_lookahead():
    times = [
        "2026-01-01T00:01",
        "2026-01-01T00:02",
        "2026-01-01T00:03",
        "2026-01-01T00:04",
        "2026-01-01T00:05",
    ]
    rows = []
    for t in times:
        rows.append(_ch_row("BTCUSDT", t, 100.0))
        rows.append(_ch_row("ETHUSDT", t, 10.0))
    ch_reader = CHReader(FakeCHClient(responses=[pd.DataFrame(rows)]))
    universe = _FakeUniverse(["BTCUSDT", "ETHUSDT"])

    # start/end 只覆盖后 3 根，但 lookback_bars=2 要求的 padding 会把前面的 bar 也一并拉回来，
    # 使得区间刚开始的 event 也能拿到完整 2 根的窗口（设计文档 5.6 padding 说明）。
    source = HistoricalPanelSource(
        ch_reader,
        universe=universe,
        interval="1m",
        start_time="2026-01-01T00:03",
        end_time="2026-01-01T00:05",
        lookback_bars=2,
    )

    events = list(source)
    assert [e.bar_start_time for e in events] == [pd.Timestamp(t, tz="UTC") for t in times[2:]]
    for e in events:
        assert len(e.panel.index) == 2
        assert e.panel.index.max() == e.bar_start_time  # 严格无未来数据
        assert e.symbols_count == 2
        assert e.coverage_ratio == 1.0
        assert e.bar_end_time == e.bar_start_time + pd.Timedelta(minutes=1) - pd.Timedelta(milliseconds=1)


def test_historical_panel_source_empty_universe_yields_nothing():
    ch_reader = CHReader(FakeCHClient(responses=[]))
    universe = _FakeUniverse([])
    source = HistoricalPanelSource(
        ch_reader,
        universe=universe,
        interval="1m",
        start_time="2026-01-01",
        end_time="2026-01-02",
    )
    assert list(source) == []


def test_live_panel_source_1m_uses_window_cache():
    redis_client = FakeRedisClient()
    redis_client.lists["kline:BTCUSDT:1m"] = [json.dumps([60_000, 1, 2, 0, 1, 10, 100, 5, 50, 1])]
    redis_client.push_kline_ready(interval="1m", timestamp_ms=60_000, symbols_count=1)

    ch_reader = CHReader(FakeCHClient(responses=[]))
    redis_reader = RedisReader(redis_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = LivePanelSource(ch_reader, redis_reader, universe=universe, intervals=["1m"])
    event = next(iter(source))

    assert event.interval == "1m"
    assert event.bar_start_time == pd.Timestamp(60_000, unit="ms", tz="UTC")


def test_live_panel_source_coarse_interval_queries_clickhouse_each_time():
    redis_client = FakeRedisClient()
    # kline_ready 里的 symbols_count 是"借来的"，应该被查询结果重算取代(设计文档 5.4/5.5)。
    redis_client.push_kline_ready(interval="1h", timestamp_ms=3_600_000, symbols_count=999)

    rows = [_ch_row("BTCUSDT", "2026-01-01T01:00:00", 100.0)]
    ch_client = FakeCHClient(responses=[pd.DataFrame(rows)])
    ch_reader = CHReader(ch_client)
    redis_reader = RedisReader(redis_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = LivePanelSource(ch_reader, redis_reader, universe=universe, intervals=["1h"])
    event = next(iter(source))

    assert len(ch_client.queries) == 1
    assert "LIMIT 200 BY symbol" in ch_client.queries[0]
    assert event.symbols_count == 1
    assert event.schema_notes["notified_symbols_count"] == 999
    assert event.schema_notes["coverage_source"] == "recomputed_from_ch_query"


def test_historical_panel_source_include_open_interest_off_by_default():
    rows = [_ch_row("BTCUSDT", "2026-01-01T00:00", 100.0)]
    ch_client = FakeCHClient(responses=[pd.DataFrame(rows)])
    ch_reader = CHReader(ch_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = HistoricalPanelSource(
        ch_reader, universe=universe, interval="5m", start_time="2026-01-01", end_time="2026-01-01T00:00"
    )
    events = list(source)

    assert len(ch_client.queries) == 1  # 没打开开关，不应该多发 OI 查询
    assert events[0].panel.open_interest is None


def test_historical_panel_source_include_open_interest_attaches_oi():
    kline_rows = [_ch_row("BTCUSDT", "2026-01-01T00:00", 100.0)]
    oi_rows = [{"symbol": "BTCUSDT", "start_time": "2026-01-01T00:00", "open_interest": 5000.0}]
    ch_client = FakeCHClient(responses=[pd.DataFrame(kline_rows), pd.DataFrame(oi_rows)])
    ch_reader = CHReader(ch_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = HistoricalPanelSource(
        ch_reader,
        universe=universe,
        interval="5m",
        start_time="2026-01-01",
        end_time="2026-01-01T00:00",
        include_open_interest=True,
    )
    events = list(source)

    assert len(ch_client.queries) == 2
    assert "market.fapi_oi_5m" in ch_client.queries[1]
    assert events[0].panel.open_interest.loc[pd.Timestamp("2026-01-01T00:00", tz="UTC"), "BTCUSDT"] == 5000.0


def test_historical_panel_source_include_open_interest_skips_1m():
    rows = [_ch_row("BTCUSDT", "2026-01-01T00:00", 100.0)]
    ch_client = FakeCHClient(responses=[pd.DataFrame(rows)])
    ch_reader = CHReader(ch_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = HistoricalPanelSource(
        ch_reader,
        universe=universe,
        interval="1m",
        start_time="2026-01-01",
        end_time="2026-01-01T00:00",
        include_open_interest=True,
    )
    events = list(source)

    assert len(ch_client.queries) == 1  # 1m 没有 OI 来源，不应该多发查询
    assert events[0].panel.open_interest is None


def test_live_panel_source_coarse_interval_include_open_interest():
    redis_client = FakeRedisClient()
    redis_client.push_kline_ready(interval="1h", timestamp_ms=3_600_000, symbols_count=1)

    kline_rows = [_ch_row("BTCUSDT", "2026-01-01T01:00:00", 100.0)]
    oi_rows = [{"symbol": "BTCUSDT", "start_time": "2026-01-01T01:00:00", "open_interest": 7000.0}]
    ch_client = FakeCHClient(responses=[pd.DataFrame(kline_rows), pd.DataFrame(oi_rows)])
    ch_reader = CHReader(ch_client)
    redis_reader = RedisReader(redis_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = LivePanelSource(
        ch_reader, redis_reader, universe=universe, intervals=["1h"], include_open_interest=True
    )
    event = next(iter(source))

    assert len(ch_client.queries) == 2
    assert event.panel.open_interest.loc[pd.Timestamp("2026-01-01T01:00:00", tz="UTC"), "BTCUSDT"] == 7000.0


def test_live_panel_source_filters_unwanted_intervals():
    redis_client = FakeRedisClient()
    redis_client.push_kline_ready(interval="5m", timestamp_ms=300_000, symbols_count=1)  # 未订阅，应跳过
    redis_client.lists["kline:BTCUSDT:1m"] = [json.dumps([60_000, 1, 2, 0, 1, 10, 100, 5, 50, 1])]
    redis_client.push_kline_ready(interval="1m", timestamp_ms=60_000, symbols_count=1)

    ch_reader = CHReader(FakeCHClient(responses=[]))
    redis_reader = RedisReader(redis_client)
    universe = _FakeUniverse(["BTCUSDT"])

    source = LivePanelSource(ch_reader, redis_reader, universe=universe, intervals=["1m"])
    event = next(iter(source))
    assert event.interval == "1m"
