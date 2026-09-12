import pytest

from sherpa.alpha.base import Alpha
from sherpa.alpha.engine import AlphaEngine

from .fixtures import make_panel


class _Close(Alpha):
    name = "close"
    family = "custom"
    min_lookback = 1

    def compute(self, panel):
        return panel.close


class _Volume(Alpha):
    name = "volume"
    family = "custom"
    min_lookback = 5

    def compute(self, panel):
        return panel.volume


def test_engine_compute_shape_and_columns():
    panel = make_panel(n=10)
    engine = AlphaEngine([_Close(), _Volume()])
    features = engine.compute(panel)

    assert list(features.index) == list(panel.symbols)
    assert set(features.columns) == {"custom.close", "custom.volume"}
    assert (features["custom.close"] == panel.close.iloc[-1]).all()


def test_engine_compute_history_returns_full_frames():
    panel = make_panel(n=10)
    engine = AlphaEngine([_Close()])
    history = engine.compute_history(panel)
    assert set(history.keys()) == {"custom.close"}
    assert history["custom.close"].shape == panel.close.shape


def test_engine_required_lookback_is_max_of_alphas():
    engine = AlphaEngine([_Close(), _Volume()])
    assert engine.required_lookback == 5


def test_engine_required_lookback_defaults_to_one_when_empty():
    engine = AlphaEngine([])
    assert engine.required_lookback == 1


def test_engine_rejects_duplicate_qualified_names():
    with pytest.raises(ValueError):
        AlphaEngine([_Close(), _Close()])
