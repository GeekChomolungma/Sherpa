import pandas as pd

from sherpa.alpha import registry
from sherpa.alpha.custom import VolumeSurge, close_momentum_20

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
