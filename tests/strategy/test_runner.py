from sherpa.alpha.base import Alpha
from sherpa.alpha.engine import AlphaEngine
from sherpa.data.schema import MarketEvent
from sherpa.strategy.base import BaseStrategy
from sherpa.strategy.runner import Runner
from sherpa.strategy.schema import TargetPosition

from tests.alpha.fixtures import make_panel

from .fakes import FakePanelSource, RecordingSink


class _Close(Alpha):
    name = "close"
    family = "custom"

    def compute(self, panel):
        return panel.close


def _make_events(n_events=3, n_bars=5, symbols=("BTCUSDT", "ETHUSDT")):
    panel = make_panel(n=n_bars, symbols=symbols)
    events = []
    for i in range(n_events):
        window = panel.slice(slice(0, n_bars - n_events + i + 1))
        events.append(
            MarketEvent.build(
                interval="1m",
                bar_start_time=window.index[-1],
                symbols_count=len(symbols),
                universe_size=len(symbols),
                panel=window,
            )
        )
    return events, list(symbols)


class _AlwaysLongStrategy(BaseStrategy):
    def setup(self):
        self.setup_called = True

    def on_bar(self, event, features):
        weights = {sym: 1.0 / len(features.index) for sym in features.index}
        return TargetPosition(weights)


class _FlatStrategy(BaseStrategy):
    def on_bar(self, event, features):
        return TargetPosition({})


class _NoOpStrategy(BaseStrategy):
    def on_bar(self, event, features):
        return None


def test_runner_calls_setup_once_before_loop():
    events, symbols = _make_events(n_events=2)
    strategy = _AlwaysLongStrategy()
    runner = Runner(strategy, AlphaEngine([_Close()]), RecordingSink())

    runner.run(FakePanelSource(events, symbols))

    assert strategy.setup_called is True


def test_runner_emits_one_intent_per_symbol_per_event():
    events, symbols = _make_events(n_events=3, symbols=("BTCUSDT", "ETHUSDT"))
    sink = RecordingSink()
    runner = Runner(_AlwaysLongStrategy(), AlphaEngine([_Close()]), sink)

    runner.run(FakePanelSource(events, symbols))

    assert sink.submit_calls == 3
    assert len(sink.received) == 3 * len(symbols)
    assert {intent.symbol for intent in sink.received} == set(symbols)
    for intent in sink.received:
        assert intent.signal_type == "target_percent"
        assert intent.strategy_id == "_AlwaysLongStrategy"


def test_runner_intent_bar_end_time_matches_event():
    events, symbols = _make_events(n_events=1)
    sink = RecordingSink()
    runner = Runner(_AlwaysLongStrategy(), AlphaEngine([_Close()]), sink)

    runner.run(FakePanelSource(events, symbols))

    assert all(intent.bar_end_time == events[0].bar_end_time for intent in sink.received)


def test_runner_skips_sink_when_strategy_returns_none():
    events, symbols = _make_events(n_events=2)
    sink = RecordingSink()
    runner = Runner(_NoOpStrategy(), AlphaEngine([_Close()]), sink)

    runner.run(FakePanelSource(events, symbols))

    assert sink.submit_calls == 0
    assert sink.received == []


def test_runner_skips_sink_when_target_has_no_weights():
    events, symbols = _make_events(n_events=2)
    sink = RecordingSink()
    runner = Runner(_FlatStrategy(), AlphaEngine([_Close()]), sink)

    runner.run(FakePanelSource(events, symbols))

    assert sink.submit_calls == 0


def test_run_backtest_and_run_live_delegate_to_run():
    events, symbols = _make_events(n_events=1)

    sink_backtest = RecordingSink()
    Runner(_AlwaysLongStrategy(), AlphaEngine([_Close()]), sink_backtest).run_backtest(
        FakePanelSource(events, symbols)
    )

    sink_live = RecordingSink()
    Runner(_AlwaysLongStrategy(), AlphaEngine([_Close()]), sink_live).run_live(FakePanelSource(events, symbols))

    assert len(sink_backtest.received) == len(sink_live.received) == len(symbols)
