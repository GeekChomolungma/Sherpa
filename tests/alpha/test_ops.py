import numpy as np
import pandas as pd
import pytest

from sherpa.alpha import ops


def _df(data, index=None):
    return pd.DataFrame(data, index=index)


def test_rank_is_cross_sectional_percentile():
    x = _df({"A": [1, 3], "B": [2, 1], "C": [3, 2]})
    result = ops.rank(x)
    # row0: A=1(min)->1/3, B=2(mid)->2/3, C=3(max)->3/3
    assert result.loc[0, "A"] == pytest.approx(1 / 3)
    assert result.loc[0, "B"] == pytest.approx(2 / 3)
    assert result.loc[0, "C"] == pytest.approx(3 / 3)


def test_scale_normalizes_row_abs_sum():
    x = _df({"A": [1.0, -2.0], "B": [3.0, 2.0]})
    result = ops.scale(x, target_sum=1.0)
    assert result.abs().sum(axis=1).tolist() == pytest.approx([1.0, 1.0])


def test_delay_and_delta():
    x = _df({"A": [1.0, 2.0, 4.0]})
    assert ops.delay(x, 1)["A"].tolist()[1:] == [1.0, 2.0]
    assert ops.delta(x, 1)["A"].tolist()[1:] == [1.0, 2.0]


def test_ts_sum_min_max():
    x = _df({"A": [1.0, 2.0, 3.0, 4.0]})
    assert ops.ts_sum(x, 2)["A"].tolist()[-2:] == [5.0, 7.0]
    assert ops.ts_min(x, 2)["A"].tolist()[-2:] == [2.0, 3.0]
    assert ops.ts_max(x, 2)["A"].tolist()[-2:] == [3.0, 4.0]


def test_ts_product_matches_manual_rolling_product():
    x = _df({"A": [1.0, 2.0, 3.0, 4.0]})
    assert ops.ts_product(x, 2)["A"].tolist()[-2:] == pytest.approx([6.0, 12.0])


def test_stddev_matches_pandas_rolling_std():
    x = _df({"A": [1.0, 2.0, 3.0, 4.0]})
    expected = x["A"].rolling(2).std()
    pd.testing.assert_series_equal(ops.stddev(x, 2)["A"], expected)


def test_ts_rank_within_window():
    x = _df({"A": [10.0, 30.0, 20.0]})
    result = ops.ts_rank(x, 3)["A"]
    # window = [10,30,20]; rank pct of last element (20) among the 3 -> 2/3
    assert result.iloc[-1] == pytest.approx(2 / 3)


def test_ts_argmax_and_argmin():
    x = _df({"A": [5.0, 9.0, 1.0, 7.0]})
    argmax = ops.ts_argmax(x, 4)["A"].iloc[-1]
    argmin = ops.ts_argmin(x, 4)["A"].iloc[-1]
    assert argmax == 1.0  # 9.0 is at position 1 within the window [5,9,1,7]
    assert argmin == 2.0  # 1.0 is at position 2


def test_ts_corr_perfectly_correlated_and_anticorrelated():
    x = _df({"A": [1.0, 2.0, 3.0, 4.0, 5.0]})
    y_pos = _df({"A": [2.0, 4.0, 6.0, 8.0, 10.0]})
    y_neg = _df({"A": [-1.0, -2.0, -3.0, -4.0, -5.0]})
    assert ops.ts_corr(x, y_pos, 3)["A"].iloc[-1] == pytest.approx(1.0)
    assert ops.ts_corr(x, y_neg, 3)["A"].iloc[-1] == pytest.approx(-1.0)


def test_ts_corr_near_zero_variance_gives_nan_not_inf():
    # y 在窗口内几乎恒定（三个值只在最后一位小数上有浮点噪声），方差趋近于 0 但不精确为 0，
    # pandas 原生 rolling().corr() 在这种输入下会算出 inf——必须收口成 NaN（世坤101
    # Alpha#68 在只有 3 个 symbol 的小截面里真实踩到过这个坑：rank() 连续几期打平）。
    x = _df({"A": [1.0, 2.0, 3.0]})
    y = _df({"A": [1.0 / 3, 1.0 / 3 + 1e-16, 1.0 / 3 - 1e-16]})
    result = ops.ts_corr(x, y, 3)["A"].iloc[-1]
    assert not np.isinf(result)
    assert np.isnan(result) or abs(result) <= 1.0


def test_decay_linear_weighted_average():
    x = _df({"A": [1.0, 2.0, 3.0]})
    result = ops.decay_linear(x, 3)["A"].iloc[-1]
    # weights = [1,2,3]/6 -> 1*(1/6) + 2*(2/6) + 3*(3/6) = (1+4+9)/6
    assert result == pytest.approx((1 + 4 + 9) / 6)


def test_signed_power_and_sign():
    x = _df({"A": [-4.0, 0.0, 9.0]})
    assert ops.signed_power(x, 2)["A"].tolist() == pytest.approx([-16.0, 0.0, 81.0])
    assert ops.sign(x)["A"].tolist() == [-1.0, 0.0, 1.0]


def test_log():
    x = _df({"A": [1.0, np.e]})
    assert ops.log(x)["A"].tolist() == pytest.approx([0.0, 1.0])


def test_adv_is_rolling_mean_of_volume():
    volume = _df({"A": [10.0, 20.0, 30.0]})
    assert ops.adv(volume, 2)["A"].tolist()[-2:] == [15.0, 25.0]


def test_vwap_is_quote_volume_over_volume():
    quote_volume = _df({"A": [200.0]})
    volume = _df({"A": [20.0]})
    assert ops.vwap(quote_volume, volume)["A"].iloc[0] == pytest.approx(10.0)


def test_indneutralize_raises_not_implemented():
    x = _df({"A": [1.0]})
    with pytest.raises(NotImplementedError):
        ops.indneutralize(x)
