import pytest

from sherpa.backtest.cost_model import FixedFeeCostModel, ZeroCostModel


def test_fixed_fee_cost_model_known_value():
    model = FixedFeeCostModel(fee_bps=5, slippage_bps=3)
    assert model.cost(turnover=1.0) == pytest.approx(8 / 10_000)


def test_zero_cost_model_is_always_zero():
    model = ZeroCostModel()
    assert model.cost(turnover=1.0) == 0.0
    assert model.cost(turnover=0.0) == 0.0
