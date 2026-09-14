import pandas as pd
import pytest

from sherpa.metrics.factor import ic_summary, is_monotonic_decreasing, quantile_returns, rank_ic


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
