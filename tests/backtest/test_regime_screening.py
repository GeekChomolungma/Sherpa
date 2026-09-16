import pandas as pd
import pytest

from sherpa.backtest.regime_screening import profile_alphas_by_regime, regime_report
from sherpa.data.schema import BarPanel


def _panel(n=100, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    from tests.alpha.fixtures import make_panel

    return make_panel(n=n, symbols=symbols)


def test_regime_report_shape_matches_panel_index():
    panel = _panel()

    report = regime_report(panel, benchmark_symbol="BTCUSDT", ma_period=5, vol_window=3, lookback=10)

    assert list(report.index) == list(panel.index)
    assert list(report.columns) == ["trend", "volatility", "dispersion", "liquidity", "regime_label"]


def test_regime_report_raises_on_unknown_benchmark():
    panel = _panel()

    with pytest.raises(KeyError):
        regime_report(panel, benchmark_symbol="NOPE")


def _regime_frame(index):
    return pd.DataFrame(
        {
            "trend": ["bull"] * (len(index) // 2) + ["bear"] * (len(index) - len(index) // 2),
            "volatility": ["normal"] * len(index),
        },
        index=index,
    )


def test_profile_alphas_by_regime_produces_long_table_per_alpha_and_dimension():
    index = pd.date_range("2026-01-01", periods=10, freq="4h", tz="UTC")
    ic_series_by_alpha = {
        "custom.a": pd.Series([0.5] * 5 + [-0.5] * 5, index=index),
        "custom.b": pd.Series([0.1] * 10, index=index),
    }
    regime = _regime_frame(index)

    profile = profile_alphas_by_regime(ic_series_by_alpha, regime, dimensions=["trend", "volatility"])

    assert set(profile["alpha"]) == {"custom.a", "custom.b"}
    assert set(profile["dimension"]) == {"trend", "volatility"}
    # 每个 (alpha, dimension) 组合都应该有一行 "ALL" 基线。
    all_rows = profile[profile["state"] == "ALL"]
    assert len(all_rows) == len(ic_series_by_alpha) * 2

    a_trend_bull = profile[(profile["alpha"] == "custom.a") & (profile["dimension"] == "trend") & (profile["state"] == "bull")]
    assert a_trend_bull["ic_mean"].iloc[0] == pytest.approx(0.5)
