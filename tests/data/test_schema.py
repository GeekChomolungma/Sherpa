import pandas as pd
import pytest

from sherpa.data.schema import (
    PANEL_FIELDS,
    BarPanel,
    MarketEvent,
    build_coverage,
    empty_panel,
    interval_to_timedelta,
)


def _make_panel(symbols=("BTCUSDT", "ETHUSDT"), n=3, interval="1m"):
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC", name="start_time")
    fields = {name: pd.DataFrame(1.0, index=index, columns=list(symbols)) for name in PANEL_FIELDS}
    coverage = pd.Series(1.0, index=index, name="coverage")
    return BarPanel(interval=interval, symbols=tuple(symbols), coverage=coverage, **fields)


def test_interval_to_timedelta():
    assert interval_to_timedelta("1m") == pd.Timedelta(minutes=1)
    assert interval_to_timedelta("1h") == pd.Timedelta(hours=1)
    with pytest.raises(ValueError):
        interval_to_timedelta("2m")


def test_barpanel_happy_path():
    panel = _make_panel()
    assert panel.symbols == ("BTCUSDT", "ETHUSDT")
    assert list(panel.index) == list(panel.open.index)
    assert panel.field("close").shape == (3, 2)
    with pytest.raises(KeyError):
        panel.field("not_a_field")


def test_barpanel_rejects_naive_index():
    index = pd.date_range("2026-01-01", periods=2, freq="1min")  # no tz
    fields = {name: pd.DataFrame(1.0, index=index, columns=["BTCUSDT"]) for name in PANEL_FIELDS}
    coverage = pd.Series(1.0, index=index)
    with pytest.raises(ValueError):
        BarPanel(interval="1m", symbols=("BTCUSDT",), coverage=coverage, **fields)


def test_barpanel_rejects_mismatched_columns():
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    fields = {name: pd.DataFrame(1.0, index=index, columns=["BTCUSDT"]) for name in PANEL_FIELDS}
    fields["close"] = pd.DataFrame(1.0, index=index, columns=["ETHUSDT"])  # mismatched
    coverage = pd.Series(1.0, index=index)
    with pytest.raises(ValueError):
        BarPanel(interval="1m", symbols=("BTCUSDT",), coverage=coverage, **fields)


def test_barpanel_rejects_duplicate_index():
    index = pd.DatetimeIndex(["2026-01-01", "2026-01-01"], tz="UTC")
    fields = {name: pd.DataFrame(1.0, index=index, columns=["BTCUSDT"]) for name in PANEL_FIELDS}
    coverage = pd.Series(1.0, index=index)
    with pytest.raises(ValueError):
        BarPanel(interval="1m", symbols=("BTCUSDT",), coverage=coverage, **fields)


def test_barpanel_tail_and_loc_until():
    panel = _make_panel(n=5)
    tail2 = panel.tail(2)
    assert len(tail2.index) == 2
    assert list(tail2.index) == list(panel.index[-2:])

    cutoff = panel.index[2]
    until = panel.loc_until(cutoff)
    assert list(until.index) == list(panel.index[:3])
    # no lookahead: nothing beyond cutoff leaks into the sliced panel
    assert until.index.max() <= cutoff


def test_empty_panel_shape():
    panel = empty_panel("5m", ["BTCUSDT", "ETHUSDT"])
    assert panel.symbols == ("BTCUSDT", "ETHUSDT")
    assert len(panel.index) == 0
    for name in PANEL_FIELDS:
        assert list(panel.field(name).columns) == ["BTCUSDT", "ETHUSDT"]


def test_build_coverage():
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    close = pd.DataFrame({"A": [1.0, None], "B": [1.0, 1.0]}, index=index)
    coverage = build_coverage(close, universe_size=2)
    assert coverage.iloc[0] == 1.0
    assert coverage.iloc[1] == 0.5

    zero_universe = build_coverage(close, universe_size=0)
    assert (zero_universe == 0.0).all()


def test_market_event_build_derives_end_time_and_coverage():
    panel = _make_panel(n=1)
    event = MarketEvent.build(
        interval="1h",
        bar_start_time="2026-01-01T10:00:00",
        symbols_count=3,
        universe_size=4,
        panel=panel,
    )
    assert event.bar_start_time == pd.Timestamp("2026-01-01T10:00:00", tz="UTC")
    assert event.bar_end_time == pd.Timestamp("2026-01-01T10:59:59.999", tz="UTC")
    assert event.coverage_ratio == pytest.approx(0.75)
    assert event.is_cold_start is False


def test_market_event_build_zero_universe_is_zero_coverage():
    panel = _make_panel(n=1)
    event = MarketEvent.build(
        interval="1m", bar_start_time="2026-01-01", symbols_count=0, universe_size=0, panel=panel
    )
    assert event.coverage_ratio == 0.0


def test_market_event_bar_end_time_matches_binance_close_time_convention():
    """close_time = open_time + duration - 1ms（例如 1m bar 是 [10:00:00.000, 10:00:59.999]），
    下一根 bar 的 start_time 必须严格等于这一根的 bar_end_time + 1ms（设计文档 5.4）。"""
    panel = _make_panel(n=1)
    this_bar = MarketEvent.build(
        interval="1m", bar_start_time="2026-01-01T10:00:00", symbols_count=1, universe_size=1, panel=panel
    )
    next_bar = MarketEvent.build(
        interval="1m", bar_start_time="2026-01-01T10:01:00", symbols_count=1, universe_size=1, panel=panel
    )
    assert this_bar.bar_end_time == pd.Timestamp("2026-01-01T10:00:59.999", tz="UTC")
    assert next_bar.bar_start_time == this_bar.bar_end_time + pd.Timedelta(milliseconds=1)
