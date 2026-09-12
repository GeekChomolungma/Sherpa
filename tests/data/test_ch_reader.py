import pandas as pd
import pytest

from sherpa.data.ch_reader import CHReader

from .fakes import FakeCHClient


def _df(rows):
    return pd.DataFrame(rows)


def test_fetch_history_lookback_uses_limit_by_and_final():
    client = FakeCHClient(responses=[_df([{"symbol": "BTCUSDT", "start_time": "2026-01-01"}])])
    reader = CHReader(client)

    reader.fetch_history(["BTCUSDT", "ETHUSDT"], "1h", lookback_bars=200)

    sql = client.queries[0]
    assert "FINAL" in sql
    assert "LIMIT 200 BY symbol" in sql
    assert "'BTCUSDT'" in sql and "'ETHUSDT'" in sql
    assert "market.fapi_kline_1h" in sql


def test_fetch_history_range_query():
    client = FakeCHClient(responses=[_df([])])
    reader = CHReader(client)

    reader.fetch_history(["BTCUSDT"], "1m", start_time="2026-01-01", end_time="2026-01-02")

    sql = client.queries[0]
    assert "FINAL" in sql
    assert "start_time >=" in sql and "start_time <=" in sql
    assert "LIMIT" not in sql


def test_fetch_history_requires_range_or_lookback():
    reader = CHReader(FakeCHClient(responses=[]))
    with pytest.raises(ValueError):
        reader.fetch_history(["BTCUSDT"], "1m")


def test_fetch_history_empty_symbols_short_circuits_without_query():
    client = FakeCHClient(responses=[])
    reader = CHReader(client)
    df = reader.fetch_history([], "1m", lookback_bars=10)
    assert df.empty
    assert client.queries == []


def test_fetch_history_rejects_unknown_interval():
    reader = CHReader(FakeCHClient(responses=[]))
    with pytest.raises(ValueError):
        reader.fetch_history(["BTCUSDT"], "2m", lookback_bars=10)


def test_get_all_symbols():
    client = FakeCHClient(responses=[_df([{"symbol": "BTCUSDT"}, {"symbol": "ETHUSDT"}])])
    reader = CHReader(client)
    assert reader.get_all_symbols() == ["BTCUSDT", "ETHUSDT"]
    assert "DISTINCT symbol" in client.queries[0]
    assert "FINAL" in client.queries[0]


def test_get_listing_times_parses_utc_timestamps():
    client = FakeCHClient(
        responses=[_df([{"symbol": "BTCUSDT", "listed_at": "2020-01-01 00:00:00"}])]
    )
    reader = CHReader(client)
    listing = reader.get_listing_times()
    assert listing["BTCUSDT"] == pd.Timestamp("2020-01-01", tz="UTC")
    assert "GROUP BY symbol" in client.queries[0]


def test_get_listing_times_empty_result():
    client = FakeCHClient(responses=[_df([])])
    reader = CHReader(client)
    assert reader.get_listing_times() == {}


def test_symbol_with_quote_is_escaped():
    client = FakeCHClient(responses=[_df([])])
    reader = CHReader(client)
    reader.fetch_history(["BTC'USDT"], "1m", lookback_bars=1)
    assert "BTC''USDT" in client.queries[0]
