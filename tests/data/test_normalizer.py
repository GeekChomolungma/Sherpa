import math

import pandas as pd
import pytest

from sherpa.data.normalizer import ch_long_to_panel, redis_rows_to_frame, redis_window_to_panel
from sherpa.data.schema import PANEL_FIELDS


def _ch_row(symbol, start_time, value=1.0, trades=10):
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
        "trades_count": trades,
    }


def test_ch_long_to_panel_basic():
    rows = [
        _ch_row("BTCUSDT", "2026-01-01T00:00:00", 100),
        _ch_row("BTCUSDT", "2026-01-01T00:01:00", 101),
        _ch_row("ETHUSDT", "2026-01-01T00:00:00", 10),
        _ch_row("ETHUSDT", "2026-01-01T00:01:00", 11),
    ]
    df = pd.DataFrame(rows)
    panel = ch_long_to_panel(df, interval="1m", symbols=["BTCUSDT", "ETHUSDT"])

    assert panel.symbols == ("BTCUSDT", "ETHUSDT")
    assert panel.close.loc["2026-01-01T00:00:00", "BTCUSDT"] == 100
    assert panel.close.loc["2026-01-01T00:01:00", "ETHUSDT"] == 11
    assert panel.trades_count.loc["2026-01-01T00:00:00", "BTCUSDT"] == 10
    assert panel.index.tz is not None
    # coverage: both symbols present at both timestamps
    assert (panel.coverage == 1.0).all()


def test_ch_long_to_panel_universe_wider_than_data():
    rows = [_ch_row("BTCUSDT", "2026-01-01T00:00:00", 100)]
    df = pd.DataFrame(rows)
    panel = ch_long_to_panel(df, interval="1m", symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    assert panel.symbols == ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    assert math.isnan(panel.close.loc["2026-01-01T00:00:00", "ETHUSDT"])
    assert panel.coverage.iloc[0] == pytest.approx(1 / 3)


def test_ch_long_to_panel_empty_input():
    df = pd.DataFrame(columns=["symbol", "start_time", *PANEL_FIELDS])
    panel = ch_long_to_panel(df, interval="1m", symbols=["BTCUSDT"])
    assert len(panel.index) == 0
    assert panel.symbols == ("BTCUSDT",)


def test_ch_long_to_panel_without_oi_df_leaves_open_interest_none():
    rows = [_ch_row("BTCUSDT", "2026-01-01T00:00:00", 100)]
    panel = ch_long_to_panel(pd.DataFrame(rows), interval="5m", symbols=["BTCUSDT"])
    assert panel.open_interest is None


def test_ch_long_to_panel_attaches_oi_aligned_to_kline_index():
    rows = [
        _ch_row("BTCUSDT", "2026-01-01T00:00:00", 100),
        _ch_row("BTCUSDT", "2026-01-01T00:05:00", 101),
        _ch_row("ETHUSDT", "2026-01-01T00:00:00", 10),
        _ch_row("ETHUSDT", "2026-01-01T00:05:00", 11),
    ]
    # OI 只覆盖 BTCUSDT 在第一根的数据——ETHUSDT、以及 BTCUSDT 第二根都应该如实留 NaN，
    # 不做任何前向填充（对齐 docs/DATA_CONSUMER_GUIDE.md §1b 的"缺失如实缺失"约定）。
    oi_rows = [{"symbol": "BTCUSDT", "start_time": "2026-01-01T00:00:00", "open_interest": 5000.0}]

    panel = ch_long_to_panel(
        pd.DataFrame(rows), interval="5m", symbols=["BTCUSDT", "ETHUSDT"], oi_df=pd.DataFrame(oi_rows)
    )

    assert panel.open_interest is not None
    assert panel.open_interest.loc["2026-01-01T00:00:00", "BTCUSDT"] == 5000.0
    assert math.isnan(panel.open_interest.loc["2026-01-01T00:05:00", "BTCUSDT"])
    assert math.isnan(panel.open_interest.loc["2026-01-01T00:00:00", "ETHUSDT"])
    # 没传 high/low 列的时候，对应字段保持 None，不会凭空造出全 NaN 的表
    assert panel.open_interest_high is None
    assert panel.open_interest_low is None


def test_ch_long_to_panel_attaches_oi_high_low_when_present():
    rows = [_ch_row("BTCUSDT", "2026-01-01T00:00:00", 100)]
    oi_rows = [
        {
            "symbol": "BTCUSDT",
            "start_time": "2026-01-01T00:00:00",
            "open_interest": 5000.0,
            "open_interest_high": 5200.0,
            "open_interest_low": 4900.0,
        }
    ]
    panel = ch_long_to_panel(
        pd.DataFrame(rows), interval="1h", symbols=["BTCUSDT"], oi_df=pd.DataFrame(oi_rows)
    )
    assert panel.open_interest_high.loc["2026-01-01T00:00:00", "BTCUSDT"] == 5200.0
    assert panel.open_interest_low.loc["2026-01-01T00:00:00", "BTCUSDT"] == 4900.0


def test_ch_long_to_panel_empty_oi_df_leaves_open_interest_none():
    rows = [_ch_row("BTCUSDT", "2026-01-01T00:00:00", 100)]
    empty_oi = pd.DataFrame(columns=["symbol", "start_time", "open_interest"])
    panel = ch_long_to_panel(pd.DataFrame(rows), interval="5m", symbols=["BTCUSDT"], oi_df=empty_oi)
    assert panel.open_interest is None


def test_ch_long_to_panel_duplicate_rows_without_final_raises():
    rows = [
        _ch_row("BTCUSDT", "2026-01-01T00:00:00", 100),
        _ch_row("BTCUSDT", "2026-01-01T00:00:00", 999),  # duplicate (symbol, start_time)
    ]
    df = pd.DataFrame(rows)
    with pytest.raises(ValueError, match="FINAL"):
        ch_long_to_panel(df, interval="1m", symbols=["BTCUSDT"])


def _redis_array(start_ms, value=1.0, trades=10):
    return [start_ms, value, value + 1, value - 1, value, value * 10, value * 100, value * 5, value * 50, trades]


def test_redis_rows_to_frame_sorts_ascending_and_dedupes():
    rows = [
        _redis_array(120_000, value=2.0),  # newest first, as Redis returns it
        _redis_array(60_000, value=1.0),
        _redis_array(60_000, value=999.0),  # duplicate ts, keep the "last" (first-seen wins by dedup rule below)
    ]
    frame = redis_rows_to_frame(rows)
    assert list(frame.index) == [
        pd.Timestamp(60_000, unit="ms", tz="UTC"),
        pd.Timestamp(120_000, unit="ms", tz="UTC"),
    ]
    assert frame["close"].iloc[-1] == 2.0


def test_redis_rows_to_frame_rejects_wrong_length():
    with pytest.raises(ValueError):
        redis_rows_to_frame([[1, 2, 3]])


def test_redis_window_to_panel_aligns_across_symbols():
    raw = {
        "BTCUSDT": [_redis_array(120_000, 2.0), _redis_array(60_000, 1.0)],
        "ETHUSDT": [_redis_array(60_000, 10.0)],  # cold-started symbol, missing the newer bar
    }
    panel = redis_window_to_panel(raw, interval="1m", symbols=["BTCUSDT", "ETHUSDT"])

    assert panel.symbols == ("BTCUSDT", "ETHUSDT")
    assert len(panel.index) == 2
    assert panel.close.loc[pd.Timestamp(120_000, unit="ms", tz="UTC"), "BTCUSDT"] == 2.0
    assert math.isnan(panel.close.loc[pd.Timestamp(120_000, unit="ms", tz="UTC"), "ETHUSDT"])
    assert panel.trades_count.loc[pd.Timestamp(60_000, unit="ms", tz="UTC"), "ETHUSDT"] == 10


def test_redis_window_to_panel_rejects_non_1m():
    with pytest.raises(ValueError):
        redis_window_to_panel({}, interval="5m", symbols=["BTCUSDT"])


def test_redis_window_to_panel_all_empty():
    panel = redis_window_to_panel({"BTCUSDT": []}, interval="1m", symbols=["BTCUSDT"])
    assert len(panel.index) == 0
    assert panel.symbols == ("BTCUSDT",)
