import json

import pandas as pd

from sherpa.data.redis_reader import KlineReadyEvent, RedisReader
from sherpa.data.window_cache import WindowCache

from .fakes import FakeRedisClient


def _array(start_ms, value=1.0, trades=10):
    return [start_ms, value, value + 1, value - 1, value, value * 10, value * 100, value * 5, value * 50, trades]


def _seed_list(client, symbol, values_newest_first):
    client.lists[f"kline:{symbol}:1m"] = [json.dumps(v) for v in values_newest_first]


def test_seed_builds_initial_panel():
    client = FakeRedisClient()
    _seed_list(client, "BTCUSDT", [_array(120_000, 2.0), _array(60_000, 1.0)])
    _seed_list(client, "ETHUSDT", [_array(120_000, 20.0), _array(60_000, 10.0)])

    cache = WindowCache(RedisReader(client), universe=["BTCUSDT", "ETHUSDT"], window_size=200)
    cache.seed()
    panel = cache._build_panel()

    assert panel.symbols == ("BTCUSDT", "ETHUSDT")
    assert len(panel.index) == 2
    assert panel.close.loc[pd.Timestamp(120_000, unit="ms", tz="UTC"), "BTCUSDT"] == 2.0


def test_on_kline_ready_appends_new_bar_and_evicts_oldest():
    client = FakeRedisClient()
    _seed_list(client, "BTCUSDT", [_array(120_000, 2.0), _array(60_000, 1.0)])

    cache = WindowCache(RedisReader(client), universe=["BTCUSDT"], window_size=2)
    cache.seed()

    # a new 1m bar just closed — the Redis list has shifted, newest now at [0]
    _seed_list(client, "BTCUSDT", [_array(180_000, 3.0), _array(120_000, 2.0), _array(60_000, 1.0)])

    event = KlineReadyEvent(entry_id="1", interval="1m", timestamp_ms=180_000, symbols_count=1)
    market_event = cache.on_kline_ready(event)

    panel = market_event.panel
    assert len(panel.index) == 2  # window_size=2, oldest (60_000) evicted
    assert list(panel.index) == [
        pd.Timestamp(120_000, unit="ms", tz="UTC"),
        pd.Timestamp(180_000, unit="ms", tz="UTC"),
    ]
    assert panel.close.loc[pd.Timestamp(180_000, unit="ms", tz="UTC"), "BTCUSDT"] == 3.0

    assert market_event.interval == "1m"
    assert market_event.bar_start_time == pd.Timestamp(180_000, unit="ms", tz="UTC")
    assert market_event.bar_end_time == pd.Timestamp(180_000, unit="ms", tz="UTC") + pd.Timedelta(
        minutes=1
    ) - pd.Timedelta(milliseconds=1)
    assert market_event.symbols_count == 1
    assert market_event.coverage_ratio == 1.0


def test_on_kline_ready_is_idempotent_for_same_bar():
    client = FakeRedisClient()
    _seed_list(client, "BTCUSDT", [_array(60_000, 1.0)])

    cache = WindowCache(RedisReader(client), universe=["BTCUSDT"], window_size=200)
    cache.seed()

    _seed_list(client, "BTCUSDT", [_array(120_000, 2.0), _array(60_000, 1.0)])
    event = KlineReadyEvent(entry_id="1", interval="1m", timestamp_ms=120_000, symbols_count=1)
    cache.on_kline_ready(event)
    cache.on_kline_ready(event)  # duplicate notification for the same bar

    panel = cache._build_panel()
    assert len(panel.index) == 2  # not 3 — the duplicate append was skipped


def test_on_kline_ready_seeds_lazily_if_not_seeded():
    client = FakeRedisClient()
    _seed_list(client, "BTCUSDT", [_array(60_000, 1.0)])

    cache = WindowCache(RedisReader(client), universe=["BTCUSDT"], window_size=200)
    event = KlineReadyEvent(entry_id="1", interval="1m", timestamp_ms=60_000, symbols_count=1)

    market_event = cache.on_kline_ready(event)
    assert len(market_event.panel.index) == 1


def test_on_kline_ready_rejects_wrong_interval():
    client = FakeRedisClient()
    cache = WindowCache(RedisReader(client), universe=["BTCUSDT"], window_size=200)
    event = KlineReadyEvent(entry_id="1", interval="5m", timestamp_ms=0, symbols_count=1)
    try:
        cache.on_kline_ready(event)
        assert False, "should have raised"
    except ValueError:
        pass


def test_new_symbol_missing_latest_bar_stays_nan():
    client = FakeRedisClient()
    _seed_list(client, "BTCUSDT", [_array(60_000, 1.0)])
    _seed_list(client, "NEWCOIN", [])  # just listed, no bars yet

    cache = WindowCache(RedisReader(client), universe=["BTCUSDT", "NEWCOIN"], window_size=200)
    cache.seed()

    _seed_list(client, "BTCUSDT", [_array(120_000, 2.0), _array(60_000, 1.0)])
    _seed_list(client, "NEWCOIN", [_array(120_000, 5.0)])  # NEWCOIN's first ever bar

    event = KlineReadyEvent(entry_id="1", interval="1m", timestamp_ms=120_000, symbols_count=2)
    market_event = cache.on_kline_ready(event)
    panel = market_event.panel

    assert panel.close.loc[pd.Timestamp(60_000, unit="ms", tz="UTC"), "NEWCOIN"] != panel.close.loc[
        pd.Timestamp(60_000, unit="ms", tz="UTC"), "NEWCOIN"
    ]  # NaN != NaN
    assert panel.close.loc[pd.Timestamp(120_000, unit="ms", tz="UTC"), "NEWCOIN"] == 5.0
