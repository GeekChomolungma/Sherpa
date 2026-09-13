from sherpa.strategy.schema import SignalIntent, TargetPosition


def test_target_position_items_reflects_weights():
    target = TargetPosition({"BTCUSDT": 0.5, "ETHUSDT": -0.25})
    assert dict(target.items()) == {"BTCUSDT": 0.5, "ETHUSDT": -0.25}


def test_target_position_defaults_to_empty():
    target = TargetPosition()
    assert dict(target.items()) == {}


def test_signal_intent_is_frozen():
    intent = SignalIntent(
        event_id="e1",
        strategy_id="s1",
        symbol="BTCUSDT",
        signal_type="target_percent",
        target_percent=0.5,
        bar_end_time="2026-01-01T00:00:59.999Z",
        generated_at="2026-01-01T00:01:00Z",
    )
    assert intent.symbol == "BTCUSDT"
