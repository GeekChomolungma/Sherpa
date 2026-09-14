import pandas as pd
import pytest

from sherpa.backtest.cost_model import FixedFeeCostModel, ZeroCostModel
from sherpa.backtest.vectorized import run_vectorized_backtest
from sherpa.metrics.performance import sharpe_ratio

from .fixtures import panel_from_close


def test_shift_defers_target_weight_to_the_next_bar():
    """alpha 在 t0 算出的目标权重，只能在 t1 才生效——用会让符号翻转的例子确保这不是巧合。"""
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100.0, 110.0, 99.0]}, index=index)
    panel = panel_from_close(close)
    # alpha 本身就是权重（identity 映射）：t0 做多，t1 做空
    alpha_history = pd.DataFrame({"A": [1.0, -1.0, 0.5]}, index=index)

    result = run_vectorized_backtest(alpha_history, panel, lambda row: row, ZeroCostModel(), shift=1)

    # t0 无仓位（还没有更早一期的信号可以生效）
    assert result.returns.iloc[0] == pytest.approx(0.0)
    # t1 的收益由 t0 算出的 +1.0 目标决定，赶上 +10% 的涨幅
    assert result.returns.iloc[1] == pytest.approx(0.10)
    # t2 的收益由 t1 算出的 -1.0 目标决定，做空躲过了 -10% 的跌幅
    assert result.returns.iloc[2] == pytest.approx(0.10)


def test_gross_return_uses_current_effective_weight_not_previous():
    """如果 shift 逻辑写反了（用未平移的权重去乘当期收益），符号会反过来，这个用例能抓到。"""
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100.0, 110.0]}, index=index)
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [1.0, -1.0]}, index=index)

    result = run_vectorized_backtest(alpha_history, panel, lambda row: row, ZeroCostModel(), shift=1)

    assert result.returns.iloc[1] > 0


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

    assert result.returns.iloc[0] == pytest.approx(0.0)
    assert result.returns.iloc[1] == pytest.approx(0.099)
    assert result.returns.iloc[2] == pytest.approx(0.0499, rel=1e-4)
    assert result.returns.iloc[3] == pytest.approx(-0.05004762, rel=1e-4)

    assert result.turnover.iloc[0] == pytest.approx(0.0)
    assert result.turnover.iloc[1] == pytest.approx(1.0)  # 从空仓建仓，满额换手
    # target 的数值虽然三期都一样（constant_weighting），但换手不是 0——A/B 在上一期里涨跌
    # 幅不对称，实际持仓已经偏离 {0.5,-0.5}，这里量的正是"漂移-重新配平"这笔交易
    assert result.turnover.iloc[2] == pytest.approx(0.10, rel=1e-4)
    assert result.turnover.iloc[3] == pytest.approx(0.047619, rel=1e-4)


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
