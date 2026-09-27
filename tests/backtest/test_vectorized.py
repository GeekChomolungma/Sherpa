import pandas as pd
import pytest

from sherpa.backtest.cost_model import FixedFeeCostModel, ZeroCostModel
from sherpa.backtest.vectorized import run_vectorized_backtest
from sherpa.metrics.performance import sharpe_ratio

from .fixtures import panel_from_close


def test_shift_defers_target_weight_to_the_next_bar():
    """alpha 在 t0 算出的目标权重赚的是 t0->t1 的收益，结果记在决策时点 t0 这一行上
    ——用会让符号翻转的例子确保这不是巧合。"""
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100.0, 110.0, 99.0]}, index=index)
    panel = panel_from_close(close)
    # alpha 本身就是权重（identity 映射）：t0 做多，t1 做空
    alpha_history = pd.DataFrame({"A": [1.0, -1.0, 0.5]}, index=index)

    result = run_vectorized_backtest(alpha_history, panel, lambda row: row, ZeroCostModel(), shift=1)

    # 最后一行（t2）的决策还没有实现的收益，不出现在结果里
    assert list(result.returns.index) == list(index[:2])
    # t0 算出的 +1.0 目标赶上 t0->t1 的 +10% 涨幅
    assert result.returns.iloc[0] == pytest.approx(0.10)
    # t1 算出的 -1.0 目标做空，躲过了 t1->t2 的 -10% 跌幅
    assert result.returns.iloc[1] == pytest.approx(0.10)


def test_shift_two_earns_the_bar_after_the_execution_delay():
    """shift=2（执行延迟 1 根 bar）：t0 的决策赚的是 t1->t2 的收益，跟 IC 标签 forward_returns(delay=1) 同口径。"""
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100.0, 200.0, 220.0, 198.0]}, index=index)
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [1.0, -1.0, 0.0, 0.0]}, index=index)

    result = run_vectorized_backtest(alpha_history, panel, lambda row: row, ZeroCostModel(), shift=2)

    assert list(result.returns.index) == list(index[:2])
    assert result.returns.iloc[0] == pytest.approx(0.10)   # +1 × (220/200 - 1)，不是 t0->t1 的 +100%
    assert result.returns.iloc[1] == pytest.approx(0.10)   # -1 × (198/220 - 1)


def test_shift_must_be_positive():
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC", name="start_time")
    panel = panel_from_close(pd.DataFrame({"A": [1.0, 2.0, 3.0]}, index=index))
    with pytest.raises(ValueError):
        run_vectorized_backtest(pd.DataFrame({"A": [1.0] * 3}, index=index), panel, lambda row: row, ZeroCostModel(), shift=0)


def test_gross_return_uses_current_effective_weight_not_previous():
    """如果 shift 逻辑写反了（用未平移的权重去乘当期收益），符号会反过来，这个用例能抓到。"""
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100.0, 110.0]}, index=index)
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [1.0, -1.0]}, index=index)

    result = run_vectorized_backtest(alpha_history, panel, lambda row: row, ZeroCostModel(), shift=1)

    assert result.returns.iloc[0] > 0


def test_turnover_and_cost_known_value():
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0, 121.0], "B": [100.0, 90.0, 90.0, 99.0]}, index=index
    )
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [0.0] * 4, "B": [0.0] * 4}, index=index)

    def constant_weighting(_row):
        return pd.Series({"A": 0.5, "B": -0.5})

    result = run_vectorized_backtest(
        alpha_history, panel, constant_weighting, FixedFeeCostModel(fee_bps=10), shift=1
    )

    # 结果按决策时点记：第 0~2 行分别是 t0/t1/t2 决策的持仓在下一根 bar 的收益（t3 的还没实现）
    assert len(result.returns) == 3
    assert result.returns.iloc[0] == pytest.approx(0.099)
    assert result.returns.iloc[1] == pytest.approx(0.0499, rel=1e-4)
    assert result.returns.iloc[2] == pytest.approx(-0.05004762, rel=1e-4)

    assert result.turnover.iloc[0] == pytest.approx(1.0)  # 从空仓建仓，满额换手
    # target 的数值虽然三期都一样（constant_weighting），但换手不是 0——A/B 在上一期里涨跌
    # 幅不对称，实际持仓已经偏离 {0.5,-0.5}，这里量的正是"漂移-重新配平"这笔交易
    assert result.turnover.iloc[1] == pytest.approx(0.10, rel=1e-4)
    assert result.turnover.iloc[2] == pytest.approx(0.047619, rel=1e-4)


def test_zero_cost_model_gives_higher_returns_than_fixed_fee():
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0, 121.0], "B": [100.0, 90.0, 90.0, 99.0]}, index=index
    )
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [0.0] * 4, "B": [0.0] * 4}, index=index)

    def constant_weighting(_row):
        return pd.Series({"A": 0.5, "B": -0.5})

    free = run_vectorized_backtest(alpha_history, panel, constant_weighting, ZeroCostModel())
    fee = run_vectorized_backtest(alpha_history, panel, constant_weighting, FixedFeeCostModel(fee_bps=10))

    assert free.equity_curve.iloc[-1] > fee.equity_curve.iloc[-1]


def test_result_sharpe_is_consistent_with_metrics_module():
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100.0, 110.0, 121.0, 133.1]}, index=index)
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [1.0, 1.0, 1.0, 1.0]}, index=index)

    result = run_vectorized_backtest(alpha_history, panel, lambda row: row, ZeroCostModel())

    periods_per_year = pd.Timedelta(days=365) / pd.Timedelta(minutes=1)
    expected_sharpe = sharpe_ratio(result.returns, periods_per_year=periods_per_year)
    if pd.isna(expected_sharpe):
        assert pd.isna(result.sharpe)
    else:
        assert result.sharpe == pytest.approx(expected_sharpe)


# ---------------------------------------------------------------------------
# numpy 递推 vs 旧的逐 bar pandas 写法；rebalance_every
# ---------------------------------------------------------------------------

def _legacy_run(alpha_history, panel, weighting_fn, cost_model, shift=1):
    """改写成 numpy 之前的实现（逐 bar 调 drift_weights / turnover），只留在测试里做口径对照。

    旧实现按"收益实现的时点"记行（把权重往后推 shift 行），开头 shift 行是空仓；新实现按决策时点记行，
    所以两者的数值应该满足：新结果 = 旧结果去掉开头 shift 行（见下面的对照测试）。
    """
    from sherpa.portfolio.turnover import drift_weights, turnover

    target = pd.DataFrame({t: weighting_fn(alpha_history.loc[t]) for t in alpha_history.index}).T
    target = target.reindex(columns=panel.close.columns, fill_value=0.0)
    effective = target.shift(shift)
    period_returns = panel.close.pct_change()
    common = effective.index.intersection(period_returns.index)
    prev_w = pd.Series(0.0, index=panel.close.columns)
    prev_r = pd.Series(0.0, index=panel.close.columns)
    nets, tos = [], []
    for t in common:
        ew = effective.loc[t].fillna(0.0)
        r = period_returns.loc[t]
        drifted = drift_weights(prev_w, prev_r)
        to = turnover(ew, drifted)
        nets.append(float((ew * r.fillna(0.0)).sum()) - cost_model.cost(to))
        tos.append(to)
        prev_w, prev_r = ew, r.fillna(0.0)
    return pd.Series(nets, index=common), pd.Series(tos, index=common)


def _random_case(seed=0, periods=60, n=8):
    import numpy as np

    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=periods, freq="4h", tz="UTC", name="start_time")
    cols = [f"S{i}" for i in range(n)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (periods, n)), axis=0)), index=index, columns=cols)
    close.iloc[5:9, 2] = float("nan")  # 停牌 / 缺数据
    alpha = pd.DataFrame(rng.normal(size=(periods, n)), index=index, columns=cols)
    alpha.iloc[10:14, 3] = float("nan")
    return panel_from_close(close, interval="4h"), alpha


@pytest.mark.parametrize("shift", [1, 2])
def test_numpy_recursion_matches_legacy_pandas_loop(shift):
    import numpy as np

    from sherpa.portfolio.weighting import demean_l1

    panel, alpha = _random_case()
    cost = FixedFeeCostModel(fee_bps=5, slippage_bps=3)
    result = run_vectorized_backtest(alpha, panel, demean_l1, cost, shift=shift)
    legacy_net, legacy_to = _legacy_run(alpha, panel, demean_l1, cost, shift=shift)

    # 同一条持仓路径，只是时间标签往前挪了 shift 行：新结果第 t 行 = 旧结果第 t+shift 行
    assert (legacy_net.iloc[:shift] == 0.0).all()
    assert list(result.returns.index) == list(alpha.index[:-shift])
    np.testing.assert_allclose(result.returns.to_numpy(), legacy_net.iloc[shift:].to_numpy(), rtol=1e-12, atol=1e-15)
    np.testing.assert_allclose(result.turnover.to_numpy(), legacy_to.iloc[shift:].to_numpy(), rtol=1e-12, atol=1e-15)


def test_rebalance_every_holds_drifted_positions_between_rebalances():
    """非调仓 bar 不交易：换手严格为 0，收益 = 漂移后持仓 × 当期收益。"""
    from sherpa.portfolio.weighting import demean_l1

    panel, alpha = _random_case(seed=1)
    result = run_vectorized_backtest(alpha, panel, demean_l1, ZeroCostModel(), shift=1, rebalance_every=3)

    # alpha 第 0、3、6…… 行是调仓行；结果按决策时点记行，调仓就发生在这些行上
    trade_rows = [i for i in range(len(result.turnover)) if i % 3 == 0]
    hold_rows = [i for i in range(len(result.turnover)) if i % 3 != 0]
    assert (result.turnover.iloc[hold_rows] == 0.0).all()
    assert (result.turnover.iloc[trade_rows] > 0.0).all()


def test_rebalance_every_differs_from_forward_filled_targets():
    """前向填充目标权重会在每根 bar 配平漂移、产生额外换手；真正的"不调仓"没有这笔换手。"""
    from sherpa.portfolio.weighting import demean_l1

    panel, alpha = _random_case(seed=2)
    held = run_vectorized_backtest(alpha, panel, demean_l1, ZeroCostModel(), rebalance_every=4)
    stale_alpha = alpha.copy()
    stale_alpha.iloc[[i for i in range(len(alpha)) if i % 4 != 0]] = float("nan")
    stale_alpha = stale_alpha.ffill()
    refilled = run_vectorized_backtest(stale_alpha, panel, demean_l1, ZeroCostModel(), rebalance_every=1)

    assert held.turnover.sum() < refilled.turnover.sum()


def test_rebalance_every_must_be_positive():
    panel, alpha = _random_case()
    with pytest.raises(ValueError):
        run_vectorized_backtest(alpha, panel, lambda row: row, ZeroCostModel(), rebalance_every=0)
