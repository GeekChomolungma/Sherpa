import pandas as pd
import pytest

from sherpa.portfolio.weighting import demean_l1, equal_weight, top_k_long_short


def test_demean_l1_is_dollar_neutral_and_leverage_one():
    alpha = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    weights = demean_l1(alpha)

    assert weights.sum() == pytest.approx(0.0)
    assert weights.abs().sum() == pytest.approx(1.0)
    # 越高的 alpha 分数应该拿到越大的正权重
    assert weights["C"] > weights["B"] > weights["A"]


def test_demean_l1_all_equal_alpha_gives_zero_weights():
    alpha = pd.Series({"A": 5.0, "B": 5.0, "C": 5.0})
    weights = demean_l1(alpha)
    assert (weights == 0.0).all()


def test_demean_l1_ignores_missing_symbols():
    alpha = pd.Series({"A": 1.0, "B": float("nan"), "C": 3.0})
    weights = demean_l1(alpha)
    assert weights["B"] == 0.0
    assert weights.abs().sum() == pytest.approx(1.0)


def test_top_k_long_short_splits_extremes():
    alpha = pd.Series({"A": 5.0, "B": 4.0, "C": 3.0, "D": 2.0, "E": 1.0})
    weights = top_k_long_short(alpha, k=2)

    assert weights["A"] == pytest.approx(0.5)
    assert weights["B"] == pytest.approx(0.5)
    assert weights["D"] == pytest.approx(-0.5)
    assert weights["E"] == pytest.approx(-0.5)
    assert weights["C"] == 0.0
    # 每条腿（多/空）各自的敞口是 1.0，不是 demean_l1 那种整体 L1=1 的约束
    assert weights[weights > 0].sum() == pytest.approx(1.0)
    assert weights[weights < 0].sum() == pytest.approx(-1.0)


def test_top_k_long_short_requires_enough_symbols():
    alpha = pd.Series({"A": 1.0, "B": 2.0, "C": 3.0})
    with pytest.raises(ValueError):
        top_k_long_short(alpha, k=2)


def test_top_k_long_short_rejects_non_positive_k():
    with pytest.raises(ValueError):
        top_k_long_short(pd.Series({"A": 1.0}), k=0)


def test_equal_weight_splits_by_sign():
    alpha = pd.Series({"A": 1.0, "B": -1.0, "C": 2.0, "D": -2.0})
    weights = equal_weight(alpha)

    assert weights["A"] == pytest.approx(0.25)
    assert weights["C"] == pytest.approx(0.25)
    assert weights["B"] == pytest.approx(-0.25)
    assert weights["D"] == pytest.approx(-0.25)


def test_equal_weight_all_missing_gives_zero_weights():
    alpha = pd.Series({"A": float("nan"), "B": float("nan")})
    weights = equal_weight(alpha)
    assert (weights == 0.0).all()
