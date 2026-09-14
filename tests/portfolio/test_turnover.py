import pandas as pd
import pytest

from sherpa.portfolio.turnover import drift_weights, turnover


def test_drift_weights_known_value():
    prev = pd.Series({"A": 0.5, "B": -0.5})
    returns = pd.Series({"A": 0.5, "B": -0.5})

    drifted = drift_weights(prev, returns)

    assert drifted["A"] == pytest.approx(0.75)
    assert drifted["B"] == pytest.approx(-0.25)
    # 漂移只改变多空之间的相对权重分布，不改变总敞口（L1 范数保持不变）
    assert drifted.abs().sum() == pytest.approx(prev.abs().sum())


def test_drift_weights_equal_moves_preserve_ratio():
    prev = pd.Series({"A": 0.5, "B": -0.5})
    returns = pd.Series({"A": 0.1, "B": 0.1})

    drifted = drift_weights(prev, returns)

    assert drifted["A"] == pytest.approx(0.5)
    assert drifted["B"] == pytest.approx(-0.5)


def test_drift_weights_flat_position_stays_flat():
    prev = pd.Series({"A": 0.0, "B": 0.0})
    returns = pd.Series({"A": 0.5, "B": -0.5})

    drifted = drift_weights(prev, returns)

    assert (drifted == 0.0).all()


def test_drift_weights_aligns_new_symbols_as_zero():
    prev = pd.Series({"A": 1.0})
    returns = pd.Series({"A": 0.0, "B": 0.0})

    drifted = drift_weights(prev, returns)

    assert drifted["B"] == 0.0


def test_turnover_known_value():
    new_weights = pd.Series({"A": 0.6, "B": -0.4})
    drifted = pd.Series({"A": 0.75, "B": -0.25})

    assert turnover(new_weights, drifted) == pytest.approx(0.3)


def test_turnover_zero_when_unchanged():
    weights = pd.Series({"A": 0.5, "B": -0.5})
    assert turnover(weights, weights) == pytest.approx(0.0)


def test_turnover_aligns_mismatched_symbols():
    new_weights = pd.Series({"A": 1.0})
    drifted = pd.Series({"B": 1.0})

    assert turnover(new_weights, drifted) == pytest.approx(2.0)
