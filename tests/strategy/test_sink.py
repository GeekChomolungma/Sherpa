import logging

import pandas as pd
import pytest

from sherpa.strategy.schema import SignalIntent
from sherpa.strategy.sink import BacktestSink, ISignalReceiver, LogSink, WebhookSink


def _make_intent(symbol="BTCUSDT") -> SignalIntent:
    now = pd.Timestamp.now(tz="UTC")
    return SignalIntent(
        event_id="e1",
        strategy_id="s1",
        symbol=symbol,
        signal_type="target_percent",
        target_percent=0.5,
        bar_end_time=now,
        generated_at=now,
    )


def test_log_sink_is_a_signal_receiver():
    assert isinstance(LogSink(), ISignalReceiver)


def test_log_sink_logs_each_intent(caplog):
    sink = LogSink()
    with caplog.at_level(logging.INFO, logger="sherpa.strategy.sink.log_sink"):
        sink.submit([_make_intent("BTCUSDT"), _make_intent("ETHUSDT")])
    assert "BTCUSDT" in caplog.text
    assert "ETHUSDT" in caplog.text


def test_log_sink_handles_empty_intents(caplog):
    sink = LogSink()
    with caplog.at_level(logging.INFO):
        sink.submit([])
    assert caplog.text == ""


class _FakeSimulator:
    """只用来验证 BacktestSink 转发行为的假 Simulator，不做任何真实换手/成本计算。"""

    def __init__(self):
        self.received: list[list[SignalIntent]] = []

    def on_intents(self, intents):
        self.received.append(list(intents))


def test_backtest_sink_is_a_signal_receiver():
    assert isinstance(BacktestSink(_FakeSimulator()), ISignalReceiver)


def test_backtest_sink_only_forwards_to_simulator_no_own_logic():
    simulator = _FakeSimulator()
    sink = BacktestSink(simulator)
    intent = _make_intent()

    sink.submit([intent])

    assert simulator.received == [[intent]]


def test_webhook_sink_is_a_signal_receiver_but_not_yet_usable():
    sink = WebhookSink()
    assert isinstance(sink, ISignalReceiver)
    with pytest.raises(NotImplementedError):
        sink.submit([_make_intent()])
