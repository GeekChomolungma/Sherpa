import pandas as pd
import pytest

import sherpa.alpha.custom  # noqa: F401  注册 custom.close_momentum_20
import sherpa.alpha.worldquant  # noqa: F401  注册占位因子 worldquant.alpha048
from sherpa.alpha import registry
from sherpa.backtest.residual import ScorePreprocessor, residual_score, residual_scores
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

from tests.alpha.fixtures import make_panel

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "BNBUSDT")
# fixture 的成交额/笔数量级很小，默认绝对地板会把所有 symbol 都掩掉；测试里放宽门槛、缩短窗口。
TRADABLE = {"lookback": 10, "seasoning_period": 5, "min_quote_volume": 0.0, "min_trades_count": 0.0, "min_percentile": 0.3}


@pytest.fixture
def panel():
    return make_panel(n=400, symbols=SYMBOLS)  # 够跑完 rolling_beta 默认窗口的 warm-up


def test_default_chain_is_mask_then_neutralize(panel):
    pre = ScorePreprocessor.from_panel(panel, benchmark_symbol="BTCUSDT", tradable=TRADABLE)
    raw = registry.get("custom.close_momentum_20")().compute(panel)

    mask = tradable_mask(panel.quote_volume, panel.trades_count, **TRADABLE)
    expected = neutralize(raw.where(mask), default_style_exposures(panel, benchmark_symbol="BTCUSDT"))

    pd.testing.assert_frame_equal(pre.mask, mask)
    pd.testing.assert_frame_equal(pre.apply(raw), expected)
    assert pre.neutralized
    assert pre.apply(raw).notna().any().any()


def test_switches_off_each_step(panel):
    raw = registry.get("custom.close_momentum_20")().compute(panel)

    identity = ScorePreprocessor.from_panel(panel, tradable=False, neutralize=False)
    assert identity.mask is None and identity.exposures is None
    pd.testing.assert_frame_equal(identity.apply(raw), raw)

    mask_only = ScorePreprocessor.from_panel(panel, tradable=TRADABLE, neutralize=False)
    pd.testing.assert_frame_equal(mask_only.apply(raw), raw.where(mask_only.mask))
    assert not mask_only.neutralized


def test_mask_labels_uses_same_mask(panel):
    labels = panel.close.pct_change().shift(-1)
    pre = ScorePreprocessor.from_panel(panel, tradable=TRADABLE)
    pd.testing.assert_frame_equal(pre.mask_labels(labels), labels.where(pre.mask))
    no_mask = ScorePreprocessor.from_panel(panel, tradable=False)
    pd.testing.assert_frame_equal(no_mask.mask_labels(labels), labels)


def test_residual_scores_batch_matches_single(panel):
    pre = ScorePreprocessor.from_panel(panel, tradable=TRADABLE)
    calls = []
    scores, errors = residual_scores(
        ["custom.close_momentum_20"], panel, pre, progress=lambda i, n, name, _: calls.append((i, n, name))
    )
    alpha = registry.get("custom.close_momentum_20")()
    pd.testing.assert_frame_equal(scores["custom.close_momentum_20"], residual_score(alpha, panel, pre))
    assert errors == {}
    assert calls == [(1, 1, "custom.close_momentum_20")]


def test_placeholder_alpha_raises_unless_skipped(panel):
    pre = ScorePreprocessor.from_panel(panel, tradable=TRADABLE)
    with pytest.raises(NotImplementedError):
        residual_scores(["worldquant.alpha048"], panel, pre)

    scores, errors = residual_scores(
        ["custom.close_momentum_20", "worldquant.alpha048"], panel, pre, skip_not_implemented=True
    )
    assert list(scores) == ["custom.close_momentum_20"]
    assert list(errors) == ["worldquant.alpha048"]


def test_unknown_name_is_a_config_error(panel):
    pre = ScorePreprocessor.from_panel(panel, tradable=False, neutralize=False)
    with pytest.raises(KeyError):
        residual_scores(["custom.does_not_exist"], panel, pre, skip_not_implemented=True)
