import numpy as np
import pandas as pd

from sherpa.backtest.style_exposure import default_style_exposures


def _panel(n=120, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT")):
    from tests.alpha.fixtures import make_panel

    return make_panel(n=n, symbols=symbols)


def test_default_style_exposures_returns_beta_and_size_aligned_to_panel():
    panel = _panel()

    exposures = default_style_exposures(panel, benchmark_symbol="BTCUSDT", beta_window=20)

    assert set(exposures.keys()) == {"beta", "size"}
    for frame in exposures.values():
        assert list(frame.index) == list(panel.index)
        assert list(frame.columns) == list(panel.symbols)


def test_default_style_exposures_size_is_log_of_quote_volume():
    panel = _panel()

    exposures = default_style_exposures(panel)

    expected = np.log(panel.quote_volume)
    pd.testing.assert_frame_equal(exposures["size"], expected)


def test_default_style_exposures_beta_is_one_for_benchmark_itself():
    panel = _panel()

    exposures = default_style_exposures(panel, benchmark_symbol="BTCUSDT", beta_window=20)

    tail = exposures["beta"]["BTCUSDT"].iloc[-5:]
    assert (tail - 1.0).abs().max() < 1e-6
