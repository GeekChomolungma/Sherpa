from dataclasses import dataclass

import pandas as pd

from sherpa.live.request import build_idempotency_key, build_live_requests


@dataclass
class FakeIntent:
    """只满足 `sherpa.live.request.SignalIntentLike` 的结构，不 import `SignalIntent`——
    用来确认 `build_live_requests` 真的是靠鸭子类型工作，不依赖 `sherpa.strategy`。"""

    strategy_id: str
    symbol: str
    target_percent: float
    bar_end_time: pd.Timestamp
    generated_at: pd.Timestamp


def _make_intent(symbol="BTCUSDT", strategy_id="s1", bar_end_time=None) -> FakeIntent:
    bar_end_time = bar_end_time or pd.Timestamp("2026-01-01T00:00:59.999Z")
    return FakeIntent(
        strategy_id=strategy_id,
        symbol=symbol,
        target_percent=0.5,
        bar_end_time=bar_end_time,
        generated_at=pd.Timestamp.now(tz="UTC"),
    )


def test_build_idempotency_key_is_deterministic():
    bar_end_time = pd.Timestamp("2026-01-01T00:00:59.999Z")
    key1 = build_idempotency_key(strategy_id="s1", symbol="BTCUSDT", bar_end_time=bar_end_time)
    key2 = build_idempotency_key(strategy_id="s1", symbol="BTCUSDT", bar_end_time=bar_end_time)
    assert key1 == key2


def test_build_idempotency_key_differs_by_strategy_symbol_or_time():
    bar_end_time = pd.Timestamp("2026-01-01T00:00:59.999Z")
    base = build_idempotency_key(strategy_id="s1", symbol="BTCUSDT", bar_end_time=bar_end_time)

    assert build_idempotency_key(strategy_id="s2", symbol="BTCUSDT", bar_end_time=bar_end_time) != base
    assert build_idempotency_key(strategy_id="s1", symbol="ETHUSDT", bar_end_time=bar_end_time) != base
    other_time = pd.Timestamp("2026-01-01T00:01:59.999Z")
    assert build_idempotency_key(strategy_id="s1", symbol="BTCUSDT", bar_end_time=other_time) != base


def test_build_live_requests_empty_input_gives_empty_output():
    assert build_live_requests([]) == []


def test_build_live_requests_maps_fields_and_idempotency_key():
    intent = _make_intent(symbol="BTCUSDT", strategy_id="s1")

    [request] = build_live_requests([intent])

    assert request.strategy_id == "s1"
    assert request.symbol == "BTCUSDT"
    assert request.target_percent == 0.5
    assert request.bar_end_time == intent.bar_end_time
    assert request.generated_at == intent.generated_at
    assert request.idempotency_key == build_idempotency_key(
        strategy_id="s1", symbol="BTCUSDT", bar_end_time=intent.bar_end_time
    )


def test_build_live_requests_replaying_same_intent_gives_same_idempotency_key():
    """幂等的核心诉求：同一个决策（同 strategy_id/symbol/bar_end_time）无论重放几次，
    算出来的 key 都一样——即便 event_id 类的随机字段每次都不同。"""
    bar_end_time = pd.Timestamp("2026-01-01T00:00:59.999Z")
    first = build_live_requests([_make_intent(bar_end_time=bar_end_time)])[0]
    second = build_live_requests([_make_intent(bar_end_time=bar_end_time)])[0]

    assert first.idempotency_key == second.idempotency_key


def test_build_live_requests_shares_one_dispatched_at_per_batch():
    intents = [_make_intent(symbol="BTCUSDT"), _make_intent(symbol="ETHUSDT")]
    requests = build_live_requests(intents)
    assert requests[0].dispatched_at == requests[1].dispatched_at


def test_build_live_requests_dispatched_at_is_now_not_generated_at():
    old_time = pd.Timestamp("2020-01-01", tz="UTC")
    intent = _make_intent()
    intent.generated_at = old_time

    [request] = build_live_requests([intent])

    assert request.generated_at == old_time
    assert request.dispatched_at > old_time
