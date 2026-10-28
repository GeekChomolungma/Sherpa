"""tradecraft alpha 的公共约定：每个注册的 tradecraft alpha 都自动跑一遍（新加的 alpha 不用另写这几条测试）。"""

import numpy as np
import pandas as pd
import pytest

from sherpa.alpha import registry
from sherpa.alpha.custom.tradecraft import TRADECRAFT_LIQUIDITY, TcDemoReversal, TradecraftAlpha
from sherpa.alpha.custom.tradecraft import indicators

from .fixtures import make_panel

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT")
TRADECRAFT = sorted(
    name for name, cls in registry.all("custom").items() if issubclass(cls, TradecraftAlpha) and cls.name
)


def _panel(n: int = 240):
    return make_panel(n=n, symbols=SYMBOLS, seed=3)


def test_there_is_at_least_one_registered_tradecraft_alpha():
    assert "custom.tc_demo_reversal" in TRADECRAFT


@pytest.mark.parametrize("qualified_name", TRADECRAFT)
def test_scores_are_point_in_time(qualified_name):
    """截掉后面的数据，前面的打分一个格子都不变：打分只用到第 t 根 K 线为止的数据。"""
    panel = _panel()
    alpha = registry.get(qualified_name)()
    full = alpha.compute(panel)
    cut = panel.index[180]
    truncated = alpha.compute(panel.loc_until(cut))
    pd.testing.assert_frame_equal(full.loc[:cut], truncated)
    assert full.notna().any().any()  # 测试面板够长，真的有打分，上面的比较才有意义


@pytest.mark.parametrize("qualified_name", TRADECRAFT)
def test_scores_only_inside_liquidity_scope(qualified_name):
    panel = _panel()
    alpha = registry.get(qualified_name)()
    scores = alpha.compute(panel)
    scope = alpha.scope(panel)
    assert scores.shape == panel.close.shape
    assert scores.where(~scope).isna().all().all()
    assert alpha.min_lookback >= max(alpha.lookback_bars, alpha.liquidity.min_lookback)
    assert alpha.params["horizon_bars"] == type(alpha).horizon_bars
    assert type(alpha).__module__.startswith("sherpa.alpha.custom.tradecraft")


def test_default_liquidity_is_the_top_half_by_quote_volume():
    assert TRADECRAFT_LIQUIDITY.min_percentile == 0.5
    assert TRADECRAFT_LIQUIDITY.enabled


def test_subclass_declarations_are_validated():
    with pytest.raises(ValueError, match="tc_"):
        type("Bad", (TradecraftAlpha,), {"name": "bad_name"})
    with pytest.raises(ValueError, match="horizon_bars"):
        type("Bad", (TradecraftAlpha,), {"name": "tc_bad", "horizon_bars": 0})
    with pytest.raises(ValueError, match="lookback_bars"):
        type("Bad", (TradecraftAlpha,), {"name": "tc_bad", "lookback_bars": 1.5})


def test_demo_reversal_is_negative_one_day_return_inside_scope():
    panel = _panel()
    alpha = TcDemoReversal()
    expected = (-panel.close.pct_change(6, fill_method=None)).where(alpha.scope(panel))
    pd.testing.assert_frame_equal(alpha.compute(panel), expected)
    assert alpha.qualified_name == "custom.tc_demo_reversal"


def test_rank_in_scope_ranks_only_symbols_in_scope():
    panel = _panel()
    alpha = TcDemoReversal()
    scope = alpha.scope(panel)
    ranked = alpha.rank_in_scope(panel.close, scope)
    row = ranked.index[-1]
    inside = scope.loc[row]
    assert ranked.loc[row][~inside].isna().all()
    assert ranked.loc[row][inside].max() == 1.0
    assert np.isclose(sorted(ranked.loc[row][inside])[0], 1 / inside.sum())


def test_indicators_basic_shapes_and_ranges():
    panel = _panel()
    position = indicators.range_position(panel, 42).dropna()
    assert ((position >= 0) & (position <= 1)).all().all()
    assert (indicators.dist_from_high(panel, 42).dropna() <= 0).all().all()
    assert (indicators.dist_from_low(panel, 42).dropna() >= 0).all().all()
    expected = panel.quote_volume.rolling(6).mean() / panel.quote_volume.rolling(42).mean()
    pd.testing.assert_frame_equal(indicators.volume_surge(panel, 6, 42), expected)
    body = indicators.candle_body_ratio(panel).dropna()
    assert ((body >= -1) & (body <= 1)).all().all()


def test_derivative_indicators_refuse_panels_without_the_field():
    panel = _panel()
    with pytest.raises(ValueError, match="open_interest"):
        indicators.oi_change(panel, 6)
    with pytest.raises(ValueError, match="long_short_ratio"):
        indicators.long_short_zscore(panel, 42)
