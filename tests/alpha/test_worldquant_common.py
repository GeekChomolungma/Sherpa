import numpy as np
import pandas as pd
import pytest

from sherpa.alpha.worldquant._common import (
    bool_to_signal,
    rank_price,
    rank_price_diff,
    rank_price_distance_from_low,
    ternary,
)


def _frame(rows, columns):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=columns)


def test_rank_price_ignores_absolute_price_level():
    # BTC 绝对价格远高于其它 symbol，但这一期相对上一期的百分比涨跌幅其实是最小的——
    # 直接 rank(price) 会把 BTC 排在最顶端；rank_price 应该按真实的相对涨跌幅排序。
    prev = _frame([[60000.0, 1.0, 0.5]], ["BTC", "ALT_A", "ALT_B"])
    curr = _frame([[60060.0, 1.05, 0.6]], ["BTC", "ALT_A", "ALT_B"])  # BTC +0.1%, A +5%, B +20%
    price = pd.concat([prev, curr])

    ranked = rank_price(price)
    last = ranked.iloc[-1]

    assert last["ALT_B"] > last["ALT_A"] > last["BTC"]


def test_rank_price_matches_raw_rank_of_pct_change():
    price = _frame(
        [[100.0, 1.0, 0.01], [102.0, 1.1, 0.008]],
        ["A", "B", "C"],
    )
    expected = price.pct_change().rank(axis=1, pct=True)
    result = rank_price(price)
    pd.testing.assert_frame_equal(result, expected)


def test_rank_price_periods_matches_delta_based_pct_change():
    price = _frame(
        [[100.0, 1.0], [101.0, 1.02], [99.0, 0.99], [105.0, 1.10]],
        ["A", "B"],
    )
    result = rank_price(price, periods=3)
    expected = price.pct_change(periods=3).rank(axis=1, pct=True)
    pd.testing.assert_frame_equal(result, expected)


def test_rank_price_first_row_is_nan():
    price = _frame([[100.0, 1.0], [102.0, 1.1]], ["A", "B"])
    result = rank_price(price)
    assert result.iloc[0].isna().all()


def test_rank_price_diff_ignores_absolute_price_level():
    # BTC 的 (a-b) 绝对差值远大于山寨币，但相对各自的 reference 而言，山寨币的偏离比例
    # 其实更大——直接 rank(a-b) 会把 BTC 排在最顶端，rank_price_diff 应该按比例排序。
    a = _frame([[60100.0, 1.05, 0.6]], ["BTC", "ALT_A", "ALT_B"])
    b = _frame([[60000.0, 1.0, 0.5]], ["BTC", "ALT_A", "ALT_B"])
    reference = b
    ranked = rank_price_diff(a, b, reference).iloc[0]
    assert ranked["ALT_B"] > ranked["ALT_A"] > ranked["BTC"]


def test_rank_price_diff_matches_raw_rank_of_ratio():
    a = _frame([[105.0, 1.1]], ["A", "B"])
    b = _frame([[100.0, 1.0]], ["A", "B"])
    reference = _frame([[100.0, 1.0]], ["A", "B"])
    expected = ((a - b) / reference).rank(axis=1, pct=True)
    pd.testing.assert_frame_equal(rank_price_diff(a, b, reference), expected)


def test_rank_price_distance_from_low_ignores_absolute_price_level():
    # BTC 离自身 3 期低点的绝对美元距离远大于山寨币，但相对低点的百分比距离其实更小。
    price = _frame(
        [[60000.0, 1.00, 0.50], [59000.0, 0.95, 0.45], [60500.0, 1.10, 0.60]],
        ["BTC", "ALT_A", "ALT_B"],
    )
    ranked = rank_price_distance_from_low(price, window=3).iloc[-1]
    assert ranked["ALT_B"] > ranked["ALT_A"] > ranked["BTC"]


def test_ternary_and_bool_to_signal_still_exported():
    # 只是确认这次改动没有意外破坏已有导出符号。
    cond = _frame([[True, False]], ["A", "B"])
    assert bool_to_signal(cond).iloc[0].tolist() == [1.0, 0.0]
    assert ternary(cond, 1.0, -1.0).iloc[0].tolist() == [1.0, -1.0]
