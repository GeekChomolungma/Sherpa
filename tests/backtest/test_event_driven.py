from dataclasses import dataclass

import pandas as pd
import pytest

from sherpa.backtest.cost_model import FixedFeeCostModel, ZeroCostModel
from sherpa.backtest.event_driven import Simulator
from sherpa.backtest.vectorized import run_vectorized_backtest

from .fixtures import panel_from_close


@dataclass
class FakeIntent:
    """只满足 `sherpa.backtest.event_driven.TargetIntent` 的结构，不 import `SignalIntent`
    ——用来确认 `Simulator` 真的是靠鸭子类型工作，不依赖 `sherpa.strategy` 的具体类型。"""

    symbol: str
    target_percent: float
    bar_end_time: pd.Timestamp


def _bar_end_time(bar_start_time: pd.Timestamp, interval: str = "1m") -> pd.Timestamp:
    return bar_start_time + pd.Timedelta(minutes=1) - pd.Timedelta(milliseconds=1)


def test_on_intents_ignores_empty_batch():
    prices = pd.DataFrame({"A": [100.0, 110.0]}, index=pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC"))
    simulator = Simulator(prices=prices, cost_model=ZeroCostModel())

    simulator.on_intents([])

    result = simulator.result()
    assert len(result.returns) == 0


def test_first_bar_has_no_position_and_no_turnover_yet():
    index = pd.date_range("2026-01-01", periods=1, freq="1min", tz="UTC")
    prices = pd.DataFrame({"A": [100.0]}, index=index)
    simulator = Simulator(prices=prices, cost_model=ZeroCostModel())

    simulator.on_intents([FakeIntent("A", 1.0, _bar_end_time(index[0]))])

    result = simulator.result()
    assert result.returns.iloc[0] == pytest.approx(0.0)
    # 建仓（FLAT -> target_0）产生的换手要等*下一次* on_intents 调用才被结算和记录
    # （配对给它实际生效的那一期收益），只发了这一次调用还看不到——见 on_intents 的 docstring。
    assert result.turnover.iloc[0] == pytest.approx(0.0)


def test_second_bar_settles_first_rebalance_turnover():
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    prices = pd.DataFrame({"A": [100.0, 110.0]}, index=index)
    simulator = Simulator(prices=prices, cost_model=ZeroCostModel())

    simulator.on_intents([FakeIntent("A", 1.0, _bar_end_time(index[0]))])
    simulator.on_intents([FakeIntent("A", -1.0, _bar_end_time(index[1]))])

    result = simulator.result()
    # FLAT -> target_0(1.0) 那笔满额换手，在这里才被结算
    assert result.turnover.iloc[1] == pytest.approx(1.0)


def test_target_takes_effect_on_the_next_bar():
    index = pd.date_range("2026-01-01", periods=3, freq="1min", tz="UTC")
    prices = pd.DataFrame({"A": [100.0, 110.0, 99.0]}, index=index)
    simulator = Simulator(prices=prices, cost_model=ZeroCostModel())

    simulator.on_intents([FakeIntent("A", 1.0, _bar_end_time(index[0]))])
    simulator.on_intents([FakeIntent("A", -1.0, _bar_end_time(index[1]))])
    simulator.on_intents([FakeIntent("A", 0.5, _bar_end_time(index[2]))])

    result = simulator.result()
    assert result.returns.iloc[0] == pytest.approx(0.0)
    assert result.returns.iloc[1] == pytest.approx(0.10)
    assert result.returns.iloc[2] == pytest.approx(0.10)


def test_event_driven_matches_vectorized_for_constant_target():
    """设计文档 §8.4.4 决策2：向量化和事件驱动两条路径必须产出同形状、同数值的结果。"""
    index = pd.date_range("2026-01-01", periods=4, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame(
        {"A": [100.0, 110.0, 121.0, 121.0], "B": [100.0, 90.0, 90.0, 99.0]}, index=index
    )
    panel = panel_from_close(close)
    alpha_history = pd.DataFrame({"A": [0.0] * 4, "B": [0.0] * 4}, index=index)

    def constant_weighting(_row):
        return pd.Series({"A": 0.5, "B": -0.5})

    cost_model = FixedFeeCostModel(fee_bps=10)
    vec_result = run_vectorized_backtest(alpha_history, panel, constant_weighting, cost_model)

    simulator = Simulator(prices=close, cost_model=cost_model, interval="1m")
    for t in index:
        end_time = _bar_end_time(t)
        simulator.on_intents([FakeIntent("A", 0.5, end_time), FakeIntent("B", -0.5, end_time)])
    event_result = simulator.result()

    pd.testing.assert_series_equal(event_result.returns, vec_result.returns, check_names=False)
    pd.testing.assert_series_equal(event_result.turnover, vec_result.turnover, check_names=False)
    assert event_result.equity_curve.iloc[-1] == pytest.approx(vec_result.equity_curve.iloc[-1])


def test_unknown_bar_end_time_treated_as_zero_return():
    index = pd.date_range("2026-01-01", periods=2, freq="1min", tz="UTC")
    prices = pd.DataFrame({"A": [100.0, 110.0]}, index=index)
    simulator = Simulator(prices=prices, cost_model=ZeroCostModel())

    # bar_end_time 对应不到 prices 里任何一根 bar 的 start_time
    bogus_time = pd.Timestamp("2099-01-01", tz="UTC")
    simulator.on_intents([FakeIntent("A", 1.0, bogus_time)])

    result = simulator.result()
    assert result.returns.iloc[0] == pytest.approx(0.0)
