import math

import numpy as np
import pandas as pd
import pytest

from sherpa.metrics.factor import (
    conditional_ic_summary,
    forward_returns,
    ic_significance,
    ic_summary,
    is_monotonic_decreasing,
    newey_west_lags,
    quantile_returns,
    rank_ic,
)


def _panel(rows):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="1min", tz="UTC")
    return pd.DataFrame(rows, index=index)


def test_rank_ic_perfect_positive_and_negative_correlation():
    alpha = _panel([{"A": 1, "B": 2, "C": 3}, {"A": 1, "B": 2, "C": 3}])
    returns = _panel([{"A": 0.1, "B": 0.2, "C": 0.3}, {"A": 0.3, "B": 0.2, "C": 0.1}])

    ic = rank_ic(alpha, returns)

    assert ic.iloc[0] == pytest.approx(1.0)
    assert ic.iloc[1] == pytest.approx(-1.0)


def test_rank_ic_insufficient_valid_points_is_nan():
    alpha = _panel([{"A": 1.0, "B": float("nan"), "C": float("nan")}])
    returns = _panel([{"A": 0.1, "B": 0.2, "C": 0.3}])

    ic = rank_ic(alpha, returns)

    assert pd.isna(ic.iloc[0])


def test_ic_summary_mean_std_and_ir():
    ic_series = pd.Series([0.1, 0.3, 0.2])
    summary = ic_summary(ic_series)

    assert summary.mean == pytest.approx(0.2)
    assert summary.ic_ir == pytest.approx(summary.mean / summary.std)


def test_ic_summary_empty_series_is_all_nan():
    summary = ic_summary(pd.Series(dtype="float64"))

    assert pd.isna(summary.mean)
    assert pd.isna(summary.ic_ir)


def test_ic_summary_zero_std_nonzero_mean_gives_infinite_ir():
    # 每一期 RankIC 都几乎完全相同且明显非零：极端稳定的强信号，IC_IR 的数学极限是 +inf，
    # 不该被判成 NaN（NaN 会让"完美因子"在 §8.4.1 的阈值判定里被误判为不通过）。
    summary = ic_summary(pd.Series([0.1, 0.1, 0.1]))

    assert summary.std == pytest.approx(0.0, abs=1e-9)
    assert summary.ic_ir == float("inf")


def test_ic_summary_zero_std_zero_mean_gives_nan_ir():
    # 真正的 0/0：每一期都没有任何相关性，没有信息可言。
    summary = ic_summary(pd.Series([0.0, 0.0, 0.0]))

    assert summary.std == pytest.approx(0.0, abs=1e-9)
    assert pd.isna(summary.ic_ir)


def test_quantile_returns_group1_is_highest_alpha():
    alpha = _panel([{"A": 1, "B": 2, "C": 3}])
    returns = _panel([{"A": 0.1, "B": 0.2, "C": 0.3}])

    q = quantile_returns(alpha, returns, n_quantiles=3)

    assert q.loc[q.index[0], 1] == pytest.approx(0.3)
    assert q.loc[q.index[0], 3] == pytest.approx(0.1)


def test_quantile_returns_insufficient_symbols_is_nan_row():
    alpha = _panel([{"A": 1.0, "B": 2.0}])
    returns = _panel([{"A": 0.1, "B": 0.2}])

    q = quantile_returns(alpha, returns, n_quantiles=5)

    assert q.iloc[0].isna().all()


def test_is_monotonic_decreasing_true_and_false():
    assert is_monotonic_decreasing(pd.Series([0.3, 0.2, 0.1])) is True
    assert is_monotonic_decreasing(pd.Series([0.1, 0.3, 0.2])) is False


def test_is_monotonic_decreasing_requires_at_least_two_points():
    assert is_monotonic_decreasing(pd.Series([0.1])) is False


def _series(values, freq="4h"):
    index = pd.date_range("2026-01-01", periods=len(values), freq=freq, tz="UTC")
    return pd.Series(values, index=index)


def test_conditional_ic_summary_splits_by_regime_and_adds_all_baseline():
    ic_series = _series([0.5, 0.5, -0.5, -0.5, 0.1])
    regime = _series(["bull", "bull", "bear", "bear", "bull"])

    report = conditional_ic_summary(ic_series, regime)

    assert set(report.index) == {"ALL", "bull", "bear"}
    assert report.loc["bull", "samples"] == 3
    assert report.loc["bull", "ic_mean"] == pytest.approx((0.5 + 0.5 + 0.1) / 3)
    assert report.loc["bear", "ic_mean"] == pytest.approx(-0.5)
    # ALL 的样本量应该正好是各分组样本量之和，不多不少。
    assert report.loc["ALL", "samples"] == report.drop(index="ALL")["samples"].sum()


def test_conditional_ic_summary_drops_rows_where_regime_is_na():
    ic_series = _series([0.2, 0.4, 0.6])
    regime = pd.Series(["bull", pd.NA, "bear"], index=ic_series.index)

    report = conditional_ic_summary(ic_series, regime)

    assert report.loc["ALL", "samples"] == 2
    assert set(report.index) == {"ALL", "bull", "bear"}


def test_conditional_ic_summary_win_rate():
    ic_series = _series([0.1, -0.1, 0.2, -0.2])
    regime = _series(["chop", "chop", "chop", "chop"])

    report = conditional_ic_summary(ic_series, regime)

    assert report.loc["chop", "win_rate"] == pytest.approx(0.5)


# ---- ic_significance（Newey–West t 检验）----

def _ar1_series(n: int, phi: float, mean: float, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, 0.05, size=n)
    values = np.empty(n)
    values[0] = noise[0]
    for i in range(1, n):
        values[i] = phi * values[i - 1] + noise[i]
    index = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC")
    return pd.Series(values + mean, index=index)


def test_ic_significance_zero_lags_matches_naive_t():
    ic = _ar1_series(500, phi=0.0, mean=0.01)
    result = ic_significance(ic, lags=0)
    clean = ic.dropna()
    # lags=0 时方差用 1/n 口径，朴素 t 用 1/(n-1)，两者只差 sqrt(n/(n-1))。
    naive = clean.mean() / (clean.std() / np.sqrt(len(clean)))
    assert result.t_stat == pytest.approx(naive * np.sqrt(len(clean) / (len(clean) - 1)), rel=1e-9)
    assert result.lags == 0
    assert result.samples == 500


def test_ic_significance_autocorrelation_shrinks_t():
    # 同样的均值，IC 序列正自相关越强，有效样本越少，Newey–West t 应该明显小于朴素 t。
    ic = _ar1_series(2000, phi=0.8, mean=0.01, seed=1)
    naive = ic_significance(ic, lags=0).t_stat
    hac = ic_significance(ic).t_stat
    assert abs(hac) < abs(naive) * 0.7


def test_ic_significance_p_value_is_two_sided_normal():
    ic = _ar1_series(1000, phi=0.0, mean=0.0, seed=2)
    result = ic_significance(ic)
    assert 0.0 <= result.p_value <= 1.0
    assert result.p_value == pytest.approx(math.erfc(abs(result.t_stat) / math.sqrt(2.0)))


def test_ic_significance_edge_cases():
    index = pd.date_range("2026-01-01", periods=5, freq="4h", tz="UTC")
    too_short = ic_significance(pd.Series([0.1, 0.2], index=index[:2]))
    assert np.isnan(too_short.t_stat) and np.isnan(too_short.p_value)

    constant = ic_significance(pd.Series([0.05] * 5, index=index))
    assert constant.t_stat == float("inf") and constant.p_value == 0.0

    all_zero = ic_significance(pd.Series([0.0] * 5, index=index))
    assert np.isnan(all_zero.t_stat)


def test_newey_west_lags_rule_of_thumb():
    assert newey_west_lags(100) == 4
    assert newey_west_lags(13000) == 11
    assert newey_west_lags(1) == 0


def test_conditional_ic_summary_includes_significance_columns():
    ic_series = _series([0.5, 0.4, -0.5, -0.4, 0.3, 0.45])
    regime = _series(["bull", "bull", "bear", "bear", "bull", "bull"])

    report = conditional_ic_summary(ic_series, regime)

    assert {"t_stat", "p_value"} <= set(report.columns)
    assert report.loc["bull", "t_stat"] > 0
    # bear 只有 2 个样本，不足 3 个，t 检验无意义，应该诚实地给 NaN。
    assert np.isnan(report.loc["bear", "t_stat"])


# ---- forward_returns（IC 标签：持有期 + 执行延迟）----

def _close_frame() -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=6, freq="4h", tz="UTC")
    return pd.DataFrame({"A": [100.0, 110.0, 99.0, 99.0, 108.9, 100.0], "B": [10.0, 10.0, 11.0, 12.1, 12.1, 13.31]}, index=index)


def test_forward_returns_default_matches_legacy_shift():
    close = _close_frame()
    pd.testing.assert_frame_equal(forward_returns(close), close.pct_change().shift(-1))


def test_forward_returns_delay_skips_one_bar():
    close = _close_frame()
    labels = forward_returns(close, delay=1)
    # t=0 的标签 = close[1] -> close[2] 的收益，而不是 close[0] -> close[1]。
    assert labels.loc[close.index[0], "A"] == pytest.approx(99.0 / 110.0 - 1)
    pd.testing.assert_frame_equal(labels, close.pct_change().shift(-2))
    assert labels.iloc[-2:].isna().all().all()


def test_forward_returns_horizon_accumulates_bars():
    close = _close_frame()
    labels = forward_returns(close, horizon=2)
    assert labels.loc[close.index[0], "B"] == pytest.approx(11.0 / 10.0 - 1)
    assert labels.iloc[-2:].isna().all().all()


def test_forward_returns_rejects_invalid_arguments():
    close = _close_frame()
    with pytest.raises(ValueError):
        forward_returns(close, horizon=0)
    with pytest.raises(ValueError):
        forward_returns(close, delay=-1)
