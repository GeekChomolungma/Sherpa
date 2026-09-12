import json

from sherpa.data.redis_reader import RedisReader

from .fakes import FakeRedisClient


def _array(start_ms, value=1.0, trades=10):
    return [start_ms, value, value + 1, value - 1, value, value * 10, value * 100, value * 5, value * 50, trades]


def test_get_closed_window_batches_symbols_in_one_pipeline():
    client = FakeRedisClient()
    client.lists["kline:BTCUSDT:1m"] = [json.dumps(_array(120_000, 2.0)), json.dumps(_array(60_000, 1.0))]
    client.lists["kline:ETHUSDT:1m"] = [json.dumps(_array(60_000, 10.0))]

    reader = RedisReader(client)
    result = reader.get_closed_window(["BTCUSDT", "ETHUSDT"], count=200)

    assert result["BTCUSDT"][0][1] == 2.0  # newest first
    assert result["ETHUSDT"] == [_array(60_000, 10.0)]


def test_get_closed_window_missing_symbol_returns_empty_list():
    client = FakeRedisClient()
    reader = RedisReader(client)
    result = reader.get_closed_window(["BTCUSDT"], count=200)
    assert result == {"BTCUSDT": []}


def test_get_latest_closed_bars():
    client = FakeRedisClient()
    client.lists["kline:BTCUSDT:1m"] = [json.dumps(_array(120_000, 2.0)), json.dumps(_array(60_000, 1.0))]
    client.lists["kline:ETHUSDT:1m"] = []

    reader = RedisReader(client)
    result = reader.get_latest_closed_bars(["BTCUSDT", "ETHUSDT"])

    assert result["BTCUSDT"] == _array(120_000, 2.0)
    assert result["ETHUSDT"] is None


def test_get_livebar():
    client = FakeRedisClient()
    client.hashes["livebar:BTCUSDT:1m"] = {"t": "60000", "c": "101.5", "x": "0"}
    reader = RedisReader(client)
    assert reader.get_livebar("BTCUSDT") == {"t": "60000", "c": "101.5", "x": "0"}
    assert reader.get_livebar("ETHUSDT") is None


def test_read_kline_ready_parses_fields():
    client = FakeRedisClient()
    client.push_kline_ready(interval="1m", timestamp_ms=60_000, symbols_count=180)
    client.push_kline_ready(interval="1h", timestamp_ms=3_600_000, symbols_count=175)

    reader = RedisReader(client)
    events = reader.read_kline_ready(last_id="$", count=10)

    assert len(events) == 2
    assert events[0].interval == "1m"
    assert events[0].timestamp_ms == 60_000
    assert events[0].symbols_count == 180
    assert events[1].interval == "1h"


def test_read_kline_ready_respects_count():
    client = FakeRedisClient()
    for i in range(5):
        client.push_kline_ready(interval="1m", timestamp_ms=i * 60_000, symbols_count=100)

    reader = RedisReader(client)
    first_batch = reader.read_kline_ready(last_id="$", count=2)
    assert len(first_batch) == 2
    second_batch = reader.read_kline_ready(last_id=first_batch[-1].entry_id, count=10)
    assert len(second_batch) == 3
