import pandas as pd

from sherpa.metrics.tradability import tradable_mask


def _frame(rows, columns):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="1D", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=columns)


def test_tradable_mask_excludes_bottom_percentile_of_cross_section():
    columns = ["ALIVE", "DEAD"]
    n = 40
    quote_volume = _frame([[1000.0, 1.0] for _ in range(n)], columns)
    trades_count = _frame([[100.0, 1.0] for _ in range(n)], columns)

    mask = tradable_mask(
        quote_volume, trades_count, lookback=10, min_percentile=0.6, seasoning_period=10
    )

    tail = mask.iloc[-1]
    assert tail["ALIVE"] is True or bool(tail["ALIVE"]) is True
    assert bool(tail["DEAD"]) is False


def test_tradable_mask_warmup_and_seasoning_default_false():
    columns = ["A", "B"]
    n = 5
    quote_volume = _frame([[100.0, 100.0] for _ in range(n)], columns)
    trades_count = _frame([[10.0, 10.0] for _ in range(n)], columns)

    mask = tradable_mask(quote_volume, trades_count, lookback=10, seasoning_period=10)

    assert not mask.to_numpy().any()


def test_tradable_mask_absolute_floor_excludes_whole_thin_cross_section():
    columns = ["A", "B", "C"]
    n = 40
    # 三个 symbol 成交额都很小（整个截面都很冷清），A 相对排名最高但绝对值仍然太低。
    quote_volume = _frame([[3.0, 2.0, 1.0] for _ in range(n)], columns)
    trades_count = _frame([[3.0, 2.0, 1.0] for _ in range(n)], columns)

    mask = tradable_mask(
        quote_volume, trades_count,
        lookback=10, min_percentile=0.5, min_quote_volume=100.0, seasoning_period=10,
    )

    assert not mask.to_numpy().any()


def test_tradable_mask_seasoning_period_blocks_fresh_listing():
    columns = ["OLD", "NEW"]
    n = 40
    old_series = [1000.0] * n
    new_series = [None] * 35 + [1000.0] * 5  # NEW 上市第 36 根 bar 才开始有数据
    quote_volume = _frame(list(zip(old_series, new_series)), columns)
    trades_count = _frame([[100.0, 100.0 if v is not None else None] for v in new_series], columns)

    mask = tradable_mask(quote_volume, trades_count, lookback=5, min_percentile=0.0, seasoning_period=10)

    assert not mask["NEW"].any()  # 上市不到 seasoning_period 根 bar，从没被判 True 过


def test_tradable_mask_causal_no_lookahead():
    columns = ["A", "B"]
    n = 60
    # 前半段 A 活跃、B 死；后半段互换。用来验证 t 时刻的判定不受"未来会互换"影响。
    a_series = [1000.0] * 30 + [1.0] * 30
    b_series = [1.0] * 30 + [1000.0] * 30
    quote_volume = _frame(list(zip(a_series, b_series)), columns)
    trades_count = _frame(list(zip([100.0] * 60, [100.0] * 60)), columns)

    full_mask = tradable_mask(quote_volume, trades_count, lookback=10, min_percentile=0.6, seasoning_period=10)
    truncated_mask = tradable_mask(
        quote_volume.iloc[:35], trades_count.iloc[:35], lookback=10, min_percentile=0.6, seasoning_period=10
    )

    pd.testing.assert_frame_equal(full_mask.iloc[:35], truncated_mask)
