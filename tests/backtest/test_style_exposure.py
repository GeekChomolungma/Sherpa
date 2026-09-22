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


def test_default_style_exposures_zero_quote_volume_gives_nan_not_negative_infinity():
    # log(0) = -inf 会直接毒死后面 neutralize() 里的 lstsq——0 成交额应该被当缺失处理，
    # 不能产出一个数值上"合法"但经济上没有意义的发散值。
    import dataclasses

    panel = _panel()
    poisoned_quote_volume = panel.quote_volume.copy()
    poisoned_quote_volume.iloc[0, 0] = 0.0
    panel = dataclasses.replace(panel, quote_volume=poisoned_quote_volume)

    exposures = default_style_exposures(panel)

    zeroed_cell = exposures["size"].iloc[0, 0]
    assert pd.isna(zeroed_cell)
    assert not np.isinf(exposures["size"].to_numpy()[~np.isnan(exposures["size"].to_numpy())]).any()
