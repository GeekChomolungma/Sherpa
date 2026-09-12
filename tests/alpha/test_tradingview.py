import pandas as pd
import pytest

from sherpa.alpha import registry
from sherpa.alpha.tradingview import ATR, RSI

from .fixtures import make_panel, make_single_symbol_panel


def test_rsi_qualified_name_includes_period():
    rsi = RSI(period=14)
    assert rsi.name == "rsi_14"
    assert rsi.qualified_name == "tradingview.rsi_14"
    assert rsi.min_lookback == 15
    assert registry.get("tradingview.rsi") is RSI


def test_rsi_monotonic_increasing_close_saturates_at_100():
    closes = [100.0 + i for i in range(20)]
    panel = make_single_symbol_panel(closes=closes, symbol="BTCUSDT")
    rsi = RSI(period=14).compute(panel)["BTCUSDT"]
    assert rsi.iloc[-1] == pytest.approx(100.0)


def test_rsi_monotonic_decreasing_close_saturates_at_0():
    closes = [100.0 - i for i in range(20)]
    panel = make_single_symbol_panel(closes=closes, symbol="BTCUSDT")
    rsi = RSI(period=14).compute(panel)["BTCUSDT"]
    assert rsi.iloc[-1] == pytest.approx(0.0)


def test_rsi_stays_within_bounds_on_random_data():
    panel = make_panel(n=40)
    rsi = RSI(period=14).compute(panel)
    valid = rsi.dropna()
    assert (valid >= 0).all().all()
    assert (valid <= 100).all().all()


def test_rsi_shape_matches_panel():
    panel = make_panel(n=20)
    result = RSI().compute(panel)
    assert result.shape == panel.close.shape


def test_atr_qualified_name_includes_period():
    atr = ATR(period=2)
    assert atr.name == "atr_2"
    assert atr.qualified_name == "tradingview.atr_2"
    assert atr.min_lookback == 3


def test_atr_hand_computed_true_range():
    closes = [10.0, 12.0, 11.0, 15.0, 14.0, 16.0]
    highs = [11.0, 13.0, 12.0, 16.0, 15.0, 17.0]
    lows = [9.0, 11.0, 10.0, 14.0, 13.0, 15.0]
    panel = make_single_symbol_panel(closes=closes, highs=highs, lows=lows, symbol="BTCUSDT")

    # 手算 true range: max(high-low, |high-prev_close|, |low-prev_close|)
    # row0 的 prev_close 不存在 -> TR 未定义 (NaN)
    expected_tr = pd.Series([float("nan"), 3.0, 2.0, 5.0, 2.0, 3.0])
    expected_atr = expected_tr.rolling(2).mean()

    result = ATR(period=2).compute(panel)["BTCUSDT"].reset_index(drop=True)
    pd.testing.assert_series_equal(result, expected_atr, check_names=False)


def test_atr_is_non_negative():
    panel = make_panel(n=30)
    atr = ATR(period=5).compute(panel)
    assert (atr.dropna() >= 0).all().all()
