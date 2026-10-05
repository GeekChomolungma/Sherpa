import numpy as np
import pandas as pd
import pytest

from sherpa.backtest.attribution import STYLE_FACTORS, attribute, period_stats, style_factor_returns


def test_attribute_recovers_known_betas_and_alpha():
    rng = np.random.default_rng(0)
    index = pd.date_range("2024-01-01", periods=3000, freq="4h", tz="UTC")
    factors = pd.DataFrame({"a": rng.normal(0, 0.01, 3000), "b": rng.normal(0, 0.01, 3000)}, index=index)
    r = 0.0005 + 0.8 * factors["a"] - 0.3 * factors["b"] + rng.normal(0, 0.002, 3000)
    out = attribute(pd.Series(r, index=index), factors, periods_per_year=2190)
    assert out["beta[a]"] == pytest.approx(0.8, abs=0.02)
    assert out["beta[b]"] == pytest.approx(-0.3, abs=0.02)
    assert out["alpha_ann"] == pytest.approx(0.0005 * 2190, rel=0.1)
    assert out["r2"] > 0.9
    # 剥离风格后剩下的 = 截距 + 噪声：Sharpe 远高于原始收益（风格贡献了大部分波动）
    assert out["alpha_sharpe"] > out["raw_sharpe"]


def test_attribute_returns_nan_on_too_few_bars():
    index = pd.date_range("2024-01-01", periods=10, freq="4h", tz="UTC")
    out = attribute(pd.Series(0.001, index=index), pd.DataFrame({"a": np.arange(10.0)}, index=index), periods_per_year=2190)
    assert np.isnan(out["alpha_sharpe"]) and out["bars"] == 10


def test_period_stats_groups_by_quarter():
    index = pd.date_range("2024-01-01", "2024-06-30 20:00", freq="4h", tz="UTC")
    r = pd.Series(0.001, index=index)
    r[r.index >= "2024-04-01"] = -0.001
    stats = period_stats(r, periods_per_year=2190)
    assert [str(p) for p in stats.index] == ["2024Q1", "2024Q2"]
    assert stats["return"].iloc[0] > 0 > stats["return"].iloc[1]


def test_style_factor_returns_columns_and_alignment():
    rng = np.random.default_rng(1)
    index = pd.date_range("2024-01-01", periods=400, freq="4h", tz="UTC")
    symbols = ["BTCUSDT"] + [f"S{i}" for i in range(29)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (400, 30)), axis=0)), index=index, columns=symbols)
    qv = pd.DataFrame(rng.uniform(1e5, 1e7, (400, 30)), index=index, columns=symbols)
    style = style_factor_returns(close, qv, None, interval="4h", shift=2, benchmark_symbol="BTCUSDT")
    assert tuple(style.columns) == STYLE_FACTORS
    assert len(style) == 400 - 2  # 最后 shift 根还没有实现的收益
    expected_btc = close["BTCUSDT"].pct_change().shift(-2).iloc[:-2]
    pd.testing.assert_series_equal(style["btc"], expected_btc, check_names=False)


def test_period_stats_blanks_stub_quarters():
    index = pd.date_range("2024-03-30", "2024-06-30 20:00", freq="4h", tz="UTC")  # 2024Q1 只有 12 根
    stats = period_stats(pd.Series(0.001, index=index), periods_per_year=2190)
    assert np.isnan(stats.loc[pd.Period("2024Q1"), "sharpe"]) and stats.loc[pd.Period("2024Q1"), "bars"] == 12
    assert np.isfinite(stats.loc[pd.Period("2024Q2"), "return"])
