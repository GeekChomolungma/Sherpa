import numpy as np
import pandas as pd

from sherpa.alpha import ops, registry
from sherpa.alpha.custom import LiquidMomentumRank
from sherpa.alpha.liquidity import LiquidityFilter, restrict
from sherpa.metrics.tradability import tradable_mask

from .fixtures import make_panel

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT")
# fixture 成交额量级小，只用相对门槛；窗口缩短，免得全被 warm-up 掩掉。
HALF = LiquidityFilter(min_percentile=0.5, lookback=10)


def _panel():
    panel = make_panel(n=80, symbols=SYMBOLS)
    panel.close.iloc[:30, -1] = np.nan  # 最后一个币晚上市
    return panel


def test_default_filter_is_the_full_cross_section():
    panel = _panel()
    f = LiquidityFilter()
    assert not f.enabled and f.min_lookback == 1
    pd.testing.assert_frame_equal(f.mask(panel), panel.close.notna())


def test_enabled_filter_delegates_to_tradable_mask():
    panel = _panel()
    expected = tradable_mask(
        panel.quote_volume, panel.trades_count, lookback=10, min_percentile=0.5,
        min_quote_volume=0.0, min_trades_count=0.0, seasoning_period=0,
    )
    assert HALF.enabled and HALF.min_lookback == 10
    pd.testing.assert_frame_equal(HALF.mask(panel), expected)
    assert expected.iloc[-1].sum() < len(SYMBOLS)  # 真的有币被排除，下面的测试才有意义


def test_restrict_masks_outside_scope():
    x = pd.DataFrame({"A": [1.0, 2.0], "B": [3.0, 4.0]})
    mask = pd.DataFrame({"A": [True, False], "B": [True, True]})
    out = restrict(x, mask)
    assert np.isnan(out.loc[1, "A"]) and out.loc[1, "B"] == 4.0


def test_liquid_momentum_rank_ranks_only_within_scope():
    panel = _panel()
    alpha = LiquidMomentumRank(window=5, liquidity=HALF)
    result = alpha.compute(panel)

    mask = HALF.mask(panel)
    momentum = panel.close.pct_change(5)
    pd.testing.assert_frame_equal(result, momentum.where(mask).rank(axis=1, pct=True) - 0.5)
    assert result.where(~mask).isna().all().all()  # 范围外全是 NaN
    # 跟全截面排名不同：范围内的币只跟范围内的币比
    full = ops.rank(momentum) - 0.5
    last = result.index[-1]
    assert not np.allclose(result.loc[last].dropna(), full.loc[last, result.loc[last].dropna().index])


def test_liquid_momentum_rank_without_filter_is_full_cross_section_rank():
    panel = _panel()
    result = LiquidMomentumRank(window=5, liquidity=LiquidityFilter()).compute(panel)
    pd.testing.assert_frame_equal(result, ops.rank(panel.close.pct_change(5)) - 0.5)


def test_liquid_momentum_rank_registered_with_defaults():
    alpha = registry.get("custom.liquid_momentum_rank")()
    assert alpha.params["liquidity"] == LiquidityFilter(min_percentile=0.5)
    assert alpha.min_lookback == LiquidityFilter().lookback
    assert type(alpha).__module__ == "sherpa.alpha.custom.starter"
