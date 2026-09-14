import pandas as pd
import pytest

from sherpa.metrics.performance import (
    annualized_return,
    calmar_ratio,
    equity_curve,
    max_drawdown,
    sharpe_ratio,
    turnover_decay,
)


def test_equity_curve_compounds_and_treats_missing_as_flat():
    returns = pd.Series([0.1, float("nan"), -0.1])
    curve = equity_curve(returns)

    assert curve.iloc[0] == pytest.approx(1.1)
    assert curve.iloc[1] == pytest.approx(1.1)
    assert curve.iloc[2] == pytest.approx(1.1 * 0.9)


def test_equity_curve_respects_initial_capital():
    curve = equity_curve(pd.Series([0.0]), initial_capital=100.0)
    assert curve.iloc[0] == pytest.approx(100.0)


def test_annualized_return_compounds_to_periods_per_year():
    returns = pd.Series([0.1, 0.1])
    result = annualized_return(returns, periods_per_year=2)
    assert result == pytest.approx(1.1 * 1.1 - 1.0)


def test_sharpe_ratio_known_value():
    returns = pd.Series([0.1, 0.2])
    sharpe = sharpe_ratio(returns, periods_per_year=2)
    assert sharpe == pytest.approx(3.0)


def test_sharpe_ratio_zero_variance_is_nan():
    returns = pd.Series([0.05, 0.05, 0.05])
    assert pd.isna(sharpe_ratio(returns, periods_per_year=252))


def test_sharpe_ratio_empty_is_nan():
    assert pd.isna(sharpe_ratio(pd.Series(dtype="float64"), periods_per_year=252))


def test_max_drawdown_known_value():
    equity = pd.Series([1.0, 1.2, 0.9, 1.1])
    assert max_drawdown(equity) == pytest.approx(-0.25)


def test_max_drawdown_empty_is_nan():
    assert pd.isna(max_drawdown(pd.Series(dtype="float64")))


def test_calmar_ratio_known_value():
    returns = pd.Series([0.1, -0.05, 0.2])
    calmar = calmar_ratio(returns, periods_per_year=3)
    assert calmar == pytest.approx(0.254 / 0.05, rel=1e-3)


def test_calmar_ratio_zero_drawdown_is_nan():
    returns = pd.Series([0.0, 0.0, 0.0])
    assert pd.isna(calmar_ratio(returns, periods_per_year=3))


def test_turnover_decay_known_value():
    gross = pd.Series([0.1, 0.1])
    net = pd.Series([0.05, 0.05])
    decay = turnover_decay(gross, net)
    assert decay == pytest.approx(1.0 - 0.1025 / 0.21, rel=1e-6)


def test_turnover_decay_nonpositive_gross_is_nan():
    gross = pd.Series([-0.1, -0.1])
    net = pd.Series([-0.2, -0.2])
    assert pd.isna(turnover_decay(gross, net))
