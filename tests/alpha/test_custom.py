import pandas as pd

from sherpa.alpha import registry
from sherpa.alpha.custom import QuoteActivityRank, VolumeSurge, close_momentum_20

from .fixtures import make_panel


def test_close_momentum_20_matches_pct_change():
    panel = make_panel(n=30)
    alpha = close_momentum_20()
    pd.testing.assert_frame_equal(alpha.compute(panel), panel.close.pct_change(20))
    assert alpha.qualified_name == "custom.close_momentum_20"
    assert registry.get("custom.close_momentum_20") is close_momentum_20


def test_volume_surge_matches_manual_formula():
    panel = make_panel(n=30)
    alpha = VolumeSurge(window=5)
    expected = panel.volume / panel.volume.rolling(5).mean() - 1
    pd.testing.assert_frame_equal(alpha.compute(panel), expected)
    assert alpha.qualified_name == "custom.volume_surge_5"
    assert alpha.min_lookback == 6


def test_volume_surge_default_window():
    alpha = VolumeSurge()
    assert alpha.qualified_name == "custom.volume_surge_20"


def test_custom_alphas_report_their_defining_module():
    """研究线按 `cls.__module__` 挑因子：函数式写法生成的类也必须记在定义它的主题模块下。"""
    assert close_momentum_20.__module__ == "sherpa.alpha.custom.starter"
    assert VolumeSurge.__module__ == "sherpa.alpha.custom.starter"


def test_quote_activity_rank_most_active_ranks_first():
    panel = make_panel(n=30, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"))
    panel.quote_volume.iloc[:, 0] *= 1000  # BTC 成交额远超其它币
    panel.quote_volume.iloc[:, -1] /= 1000  # XRP 远低于其它币
    alpha = QuoteActivityRank(window=5)
    result = alpha.compute(panel)

    expected = panel.quote_volume.rolling(5).sum().rank(axis=1, ascending=False, pct=True)
    pd.testing.assert_frame_equal(result, expected)
    assert result.iloc[:4].isna().all().all()  # 窗口没攒满
    assert (result.iloc[4:]["BTCUSDT"] == 0.25).all()  # 最活跃 = 1/N
    assert (result.iloc[4:]["XRPUSDT"] == 1.0).all()
    assert alpha.qualified_name == "custom.quote_activity_rank"
    assert registry.get("custom.quote_activity_rank") is QuoteActivityRank
    assert QuoteActivityRank.__module__ == "sherpa.alpha.custom.quote_activity"
