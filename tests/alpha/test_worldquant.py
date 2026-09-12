import math

import pandas as pd
import pytest

from sherpa.alpha import registry
from sherpa.alpha.worldquant import (
    Alpha001,
    Alpha002,
    Alpha003,
    Alpha004,
    Alpha006,
    Alpha009,
    Alpha012,
    Alpha101,
    IndustryNeutralPlaceholder,
)

from .fixtures import make_panel, make_single_symbol_panel

ALL_ALPHAS = [Alpha001, Alpha002, Alpha003, Alpha004, Alpha006, Alpha009, Alpha012, Alpha101]


@pytest.mark.parametrize("cls", ALL_ALPHAS)
def test_shape_matches_panel_and_registered(cls):
    panel = make_panel(n=40)
    alpha = cls()
    result = alpha.compute(panel)

    assert result.shape == panel.close.shape
    assert list(result.index) == list(panel.index)
    assert list(result.columns) == list(panel.symbols)
    assert registry.get(alpha.qualified_name) is cls


@pytest.mark.parametrize("cls", ALL_ALPHAS)
def test_latest_is_a_symbol_indexed_series(cls):
    panel = make_panel(n=40)
    latest = cls().latest(panel)
    assert list(latest.index) == list(panel.symbols)


# Alpha001 不满足"warmup 内严格全 NaN"：公式里 returns>=0 时直接用 close（永远有值），
# 绕开了 stddev(returns,20) 自己的 20 根 warmup，min_lookback=25 只是保守上界，不是精确边界。
_STRICT_WARMUP_ALPHAS = [a for a in ALL_ALPHAS if a is not Alpha001]


@pytest.mark.parametrize("cls", _STRICT_WARMUP_ALPHAS)
def test_warmup_is_nan_then_has_real_values(cls):
    panel = make_panel(n=40)
    alpha = cls()
    result = alpha.compute(panel)

    warmup = alpha.min_lookback - 1
    if warmup > 0:
        assert result.iloc[:warmup].isna().all().all(), f"{alpha.qualified_name} warmup should be all-NaN"
    # 过了 warmup 之后应该出现真实数值，不是继续 NaN 下去
    assert result.iloc[warmup:].notna().any().any(), f"{alpha.qualified_name} never produces a value"


def test_alpha001_eventually_produces_real_values():
    # min_lookback=25 是保守上界，只断言"最终会有值"，不断言严格的 warmup 截止点
    panel = make_panel(n=40)
    result = Alpha001().compute(panel)
    assert result.notna().any().any()
    assert result.iloc[0].isna().all()  # 第一根肯定还没有任何滚动窗口，必然是 NaN


def test_alpha101_matches_direct_formula():
    panel = make_panel(n=10)
    expected = (panel.close - panel.open) / ((panel.high - panel.low) + 0.001)
    pd.testing.assert_frame_equal(Alpha101().compute(panel), expected)


def test_alpha012_hand_computed_values():
    panel = make_single_symbol_panel(
        closes=[100.0, 102.0, 101.0, 105.0],
        volumes=[500.0, 600.0, 550.0, 700.0],
        symbol="BTCUSDT",
    )
    result = Alpha012().compute(panel)["BTCUSDT"].tolist()

    assert math.isnan(result[0])
    assert result[1:] == pytest.approx([-2.0, -1.0, -4.0])


def test_alpha009_trending_up_keeps_positive_delta():
    # 连续5根都在涨 (delta 恒为 +1)：trending=True，输出应该直接是 delta(=1)，不是反转
    closes = [100.0 + i for i in range(7)]
    panel = make_single_symbol_panel(closes=closes, symbol="BTCUSDT")
    result = Alpha009().compute(panel)["BTCUSDT"]

    # 前 5 根 (min_lookback=6, warmup=5) 应该是 NaN
    assert result.iloc[:5].isna().all()
    # 第 6 根开始，5根窗口都在涨，trending=True -> 输出 = delta = 1
    assert result.iloc[5:].tolist() == pytest.approx([1.0] * len(result.iloc[5:]))


def test_alpha009_non_trending_reverses_delta():
    # 涨跌交替：5根窗口内既有正也有负，不满足"连续5根同向"，应该输出 -delta
    closes = [100.0, 101.0, 100.0, 101.0, 100.0, 101.0, 100.0]
    panel = make_single_symbol_panel(closes=closes, symbol="BTCUSDT")
    d = pd.Series(closes).diff()
    result = Alpha009().compute(panel)["BTCUSDT"]

    last_delta = d.iloc[-1]
    assert result.iloc[-1] == pytest.approx(-1 * last_delta)


def test_cross_sectional_placeholder_raises_and_is_not_registered():
    panel = make_panel(n=5)
    with pytest.raises(NotImplementedError, match="行业分类"):
        IndustryNeutralPlaceholder().compute(panel)
    assert "worldquant.IndustryNeutralPlaceholder" not in registry.all()
