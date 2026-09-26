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
    assert set(profile["dimension"]) == {"trend", "volatility", "unconditional"}
    # 各维度不再有自己的 "ALL" 行；每个 alpha 只有一行 unconditional/ALL 作为全历史基线。
    all_rows = profile[profile["state"] == "ALL"]
    assert len(all_rows) == len(ic_series_by_alpha)
    assert set(all_rows["dimension"]) == {"unconditional"}

    a_trend_bull = profile[(profile["alpha"] == "custom.a") & (profile["dimension"] == "trend") & (profile["state"] == "bull")]
    assert a_trend_bull["ic_mean"].iloc[0] == pytest.approx(0.5)


def test_profile_alphas_by_regime_unconditional_row_uses_full_series():
    index = pd.date_range("2026-01-01", periods=10, freq="4h", tz="UTC")
    ic_series = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0], index=index)
    regime = _regime_frame(index)
    # 让 trend 维度前 3 根 bar 处于 warm-up（NA）：它的 ALL 行只剩 7 个样本，unconditional 行应该仍是 10 个。
    regime["trend"] = regime["trend"].astype(object)
    regime.iloc[:3, regime.columns.get_loc("trend")] = pd.NA

    profile = profile_alphas_by_regime({"custom.a": ic_series}, regime, dimensions=["trend"])

    unconditional = profile[profile["dimension"] == "unconditional"]
    assert len(unconditional) == 1
    row = unconditional.iloc[0]
    assert row["state"] == "ALL"
    assert row["samples"] == 10
    assert row["ic_mean"] == pytest.approx(ic_series.mean())
    assert {"t_stat", "p_value"} <= set(profile.columns)

    # trend 维度只剩具体 state 行，样本合计 7（warm-up 的 3 根不属于任何 state）。
    trend_rows = profile[profile["dimension"] == "trend"]
    assert "ALL" not in set(trend_rows["state"])
    assert trend_rows["samples"].sum() == 7
