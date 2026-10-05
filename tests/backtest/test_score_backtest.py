import numpy as np
import pandas as pd
import pytest

from sherpa.backtest.cost_model import FixedFeeCostModel, ZeroCostModel
from sherpa.backtest.score_backtest import (
    cost_segment_rows,
    cross_sectional_rank,
    run_score_backtest,
    segment_stats,
    target_path,
    weighted_composite,
)
from sherpa.backtest.vectorized import run_vectorized_backtest

from .fixtures import panel_from_close


def _close(n=60, n_symbols=8, seed=0):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC", name="start_time")
    returns = rng.normal(0, 0.02, (n, n_symbols))
    return pd.DataFrame(100 * np.exp(np.cumsum(returns, axis=0)), index=index, columns=[f"S{i}" for i in range(n_symbols)])


def test_cross_sectional_rank_is_centered_and_skips_nan():
    scores = pd.DataFrame({"A": [1.0, np.nan], "B": [2.0, 5.0], "C": [3.0, 4.0]})
    ranked = cross_sectional_rank(scores)
    assert ranked.iloc[0].tolist() == pytest.approx([1 / 3 - 0.5, 2 / 3 - 0.5, 0.5])
    assert np.isnan(ranked.iloc[1]["A"]) and ranked.iloc[1][["B", "C"]].tolist() == pytest.approx([0.5, 0.0])


def test_top_k_target_path_is_dollar_neutral_with_half_on_each_side_and_only_on_rebalance_rows():
    close = _close()
    scores = cross_sectional_rank(close.pct_change(fill_method=None))
    targets = target_path(scores, {"method": "top_k", "k": 2, "exit_k": 2}, rebalance_every=3)
    traded = targets.iloc[3::3]
    assert traded.clip(lower=0).sum(axis=1).tolist() == pytest.approx([0.5] * len(traded))
    assert traded.clip(upper=0).sum(axis=1).tolist() == pytest.approx([-0.5] * len(traded))
    off_rows = targets.drop(targets.index[::3])
    assert (off_rows == 0).all().all()  # 非调仓行填 0，回测不会用到


def test_top_k_goes_flat_when_fewer_than_2k_valid_symbols():
    close = _close(n_symbols=3)
    scores = cross_sectional_rank(close.pct_change(fill_method=None))
    targets = target_path(scores, {"method": "top_k", "k": 2, "exit_k": 2}, rebalance_every=1)
    assert (targets == 0).all().all()


def test_zero_cost_backtest_then_deduct_equals_backtesting_with_the_cost_model():
    """链的核心假设：成本只从收益里扣、不影响仓位，所以"零成本跑一次再按成本扣"跟直接带成本跑完全相同。"""
    close = _close()
    scores = cross_sectional_rank(close.pct_change(fill_method=None))
    targets = target_path(scores, {"method": "top_k", "k": 2, "exit_k": 4}, rebalance_every=3)
    cost = FixedFeeCostModel(fee_bps=5.0, slippage_bps=3.0)

    gross, turnover = run_score_backtest(targets, close, "4h", shift=2, rebalance_every=3)
    direct = run_vectorized_backtest(targets, panel_from_close(close, "4h"), lambda r: r, cost, shift=2, rebalance_every=3)
    pd.testing.assert_series_equal(gross - turnover.map(cost.cost), direct.returns, check_names=False)


def test_cost_segment_rows_cover_every_cost_and_segment_and_match_segment_stats():
    close = _close()
    scores = cross_sectional_rank(close.pct_change(fill_method=None))
    targets = target_path(scores, {"method": "top_k", "k": 2, "exit_k": 2}, rebalance_every=1)
    gross, turnover = run_score_backtest(targets, close, "4h", shift=2, rebalance_every=1)
    half = pd.Series(gross.index < gross.index[len(gross) // 2], index=gross.index)
    segments = {"first": half, "second": ~half}
    costs = {"zero": ZeroCostModel(), "taker": FixedFeeCostModel(fee_bps=8.0)}
    curves: dict = {}

    rows = cost_segment_rows(gross, turnover, costs, segments, periods_per_year=2190, net_curves=curves)

    assert [(r["cost_model"], r["segment"]) for r in rows] == [(c, s) for c in costs for s in segments]
    taker_second = next(r for r in rows if r["cost_model"] == "taker" and r["segment"] == "second")
    net = gross - turnover.map(costs["taker"].cost)
    expected = segment_stats(gross[~half], turnover[~half], net[~half], periods_per_year=2190)
    assert taker_second["net_sharpe"] == pytest.approx(expected["net_sharpe"])
    pd.testing.assert_series_equal(curves[("taker", "second")], net[~half])


def test_weighted_composite_renormalizes_over_factors_present_in_each_cell():
    a = pd.DataFrame({"X": [0.5, -0.5], "Y": [0.1, 0.2]})
    b = pd.DataFrame({"X": [-0.5, np.nan], "Y": [0.3, 0.4]})
    out = weighted_composite({"a": a, "b": b}, {"a": 1.0, "b": -3.0})
    # (0,X)：(1×0.5 + −3×−0.5) / 4；(1,X) 只有 a 有值：a 自己
    assert out.loc[0, "X"] == pytest.approx((0.5 + 1.5) / 4)
    assert out.loc[1, "X"] == pytest.approx(-0.5)
    assert out.loc[0, "Y"] == pytest.approx((0.1 - 0.9) / 4)


def test_weighted_composite_factors_select_candidates_and_zero_weights_are_skipped():
    a = pd.DataFrame({"X": [0.2]})
    b = pd.DataFrame({"X": [-0.4]})
    ranked = {"a": a, "b": b}
    weights = {"a": 1.0, "b": 1.0}
    pd.testing.assert_frame_equal(weighted_composite(ranked, weights, factors=["a"]), a)  # 只用候选名单里的
    pd.testing.assert_frame_equal(weighted_composite(ranked, {"a": 0.0, "b": -1.0}), -b)  # 权重 0 不参与
    with pytest.raises(ValueError):
        weighted_composite(ranked, {"a": 0.0, "b": 0.0})


def test_top_quantile_sizes_legs_by_the_current_cross_section():
    """相对分位：k = round(q·n)。币池从 20 个变成 40 个，每条腿的币数跟着从 2 变成 4，多空仍各 0.5。"""
    close = _close(n=30, n_symbols=40)
    close.iloc[:15, 20:] = np.nan  # 前 15 根只有 20 个币上线
    scores = cross_sectional_rank(close.pct_change(fill_method=None))
    targets = target_path(scores, {"method": "top_quantile", "q": 0.1, "exit_q": 0.3}, rebalance_every=1)
    early, late = targets.iloc[5], targets.iloc[25]
    assert (early > 0).sum() == 2 and (early < 0).sum() == 2
    assert (late > 0).sum() == 4 and (late < 0).sum() == 4
    assert late.clip(lower=0).sum() == pytest.approx(0.5) and late.clip(upper=0).sum() == pytest.approx(-0.5)
    small = target_path(scores.iloc[:, :15], {"method": "top_quantile", "q": 0.1}, rebalance_every=1)
    assert (small == 0).all().all()  # 有效币少于 min_names=20 的期空仓
    with pytest.raises(ValueError):
        target_path(scores, {"method": "top_quantile", "q": 0.3, "exit_q": 0.1}, rebalance_every=1)
