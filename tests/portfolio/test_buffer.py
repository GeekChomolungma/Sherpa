import pandas as pd
import pytest

from sherpa.portfolio.buffer import no_trade_band, top_k_hysteresis
from sherpa.portfolio.weighting import top_k_long_short


def _alpha(values):
    return pd.Series(values, index=[f"S{i}" for i in range(len(values))], dtype=float)


def test_hysteresis_equals_plain_top_k_without_buffer_or_history():
    alpha = _alpha([5, 3, 9, 1, 7, 2, 8, 4])
    expected = top_k_long_short(alpha, 2)
    pd.testing.assert_series_equal(top_k_hysteresis(alpha, None, 2, 2), expected)
    pd.testing.assert_series_equal(top_k_hysteresis(alpha, expected * 0 + expected.shift(1).fillna(0), 2, 2), expected)


def test_held_long_survives_until_it_leaves_the_exit_band():
    prev = top_k_long_short(_alpha([9, 8, 7, 6, 5, 4, 3, 2, 1, 0]), 2)  # 多 S0/S1，空 S8/S9
    # S1 掉到第 3 名：exit_k=3 时继续持有，exit_k=2 时被 S2 替换
    alpha = _alpha([9, 7, 8, 6, 5, 4, 3, 2, 1, 0])
    kept = top_k_hysteresis(alpha, prev, 2, 3)
    assert kept["S1"] == pytest.approx(0.5) and kept["S2"] == 0.0
    swapped = top_k_hysteresis(alpha, prev, 2, 2)
    assert swapped["S2"] == pytest.approx(0.5) and swapped["S1"] == 0.0
    # 跌出 exit_k 就平仓
    alpha_far = _alpha([9, 2, 8, 7, 6, 5, 4, 3, 1, 0])
    assert top_k_hysteresis(alpha_far, prev, 2, 3)["S1"] == 0.0


def test_short_leg_is_symmetric_and_legs_never_overlap():
    prev = top_k_long_short(_alpha([9, 8, 7, 6, 5, 4, 3, 2, 1, 0]), 2)
    alpha = _alpha([9, 8, 7, 6, 5, 4, 3, 1, 2, 0])  # S8 升到倒数第 3
    result = top_k_hysteresis(alpha, prev, 2, 3)
    assert result["S8"] == pytest.approx(-0.5)
    assert (result > 0).sum() == 2 and (result < 0).sum() == 2
    assert result.sum() == pytest.approx(0.0)
    # 缓冲带宽到覆盖全体时也不会出现一个 symbol 两边都占
    small = _alpha([4, 3, 2, 1])
    wide = top_k_hysteresis(small, top_k_long_short(small, 2), 2, 4)
    assert (wide > 0).sum() == 2 and (wide < 0).sum() == 2


def test_missing_alpha_forces_exit_and_insufficient_symbols_raise():
    prev = top_k_long_short(_alpha([9, 8, 7, 6, 5, 4]), 1)
    alpha = _alpha([float("nan"), 8, 7, 6, 5, 4])
    assert top_k_hysteresis(alpha, prev, 1, 3)["S0"] == 0.0
    with pytest.raises(ValueError):
        top_k_hysteresis(_alpha([1.0, float("nan"), float("nan")]), None, 1, 1)
    with pytest.raises(ValueError):
        top_k_hysteresis(_alpha([1, 2, 3, 4]), None, 2, 1)


def test_no_trade_band_freezes_small_changes_only():
    prev = pd.Series({"A": 0.30, "B": -0.30, "C": 0.20})
    target = pd.Series({"A": 0.305, "B": -0.20, "D": -0.10})
    result = no_trade_band(target, prev, band=0.01)
    assert result["A"] == pytest.approx(0.30)   # 变动 0.005 <= band，维持
    assert result["B"] == pytest.approx(-0.20)  # 变动 0.10 > band，调到目标
    assert result["C"] == pytest.approx(0.0)    # 目标里没有 = 目标 0，变动 0.20 > band
    assert result["D"] == pytest.approx(-0.10)
    pd.testing.assert_series_equal(no_trade_band(target, prev, 0.0), target)
    with pytest.raises(ValueError):
        no_trade_band(target, prev, -1.0)


def _legacy_top_k_hysteresis(alpha, prev_target, k, exit_k):
    """改写成 numpy 之前的 pandas 实现，只留在测试里做口径对照。"""
    valid = alpha.dropna()
    descending = valid.sort_values(ascending=False, kind="stable").index
    prev = prev_target.reindex(valid.index).fillna(0.0) if prev_target is not None else pd.Series(0.0, index=valid.index)
    held_long = set(prev.index[prev > 0])
    keep_long = [s for s in descending[:exit_k] if s in held_long][:k]
    longs = keep_long + [s for s in descending if s not in keep_long][: k - len(keep_long)]
    ascending = [s for s in reversed(descending) if s not in set(longs)]
    held_short = set(prev.index[prev < 0])
    keep_short = [s for s in ascending[:exit_k] if s in held_short][:k]
    shorts = keep_short + [s for s in ascending if s not in keep_short][: k - len(keep_short)]
    weights = pd.Series(0.0, index=alpha.index)
    weights.loc[longs] = 1.0 / k
    weights.loc[shorts] = -1.0 / k
    return weights


@pytest.mark.parametrize("seed", range(20))
def test_hysteresis_matches_legacy_pandas_implementation(seed):
    import numpy as np

    rng = np.random.default_rng(seed)
    n = int(rng.integers(12, 60))
    k = int(rng.integers(1, n // 2 + 1))
    exit_k = int(rng.integers(k, n + 1))
    prev = None
    for _ in range(15):
        values = np.round(rng.normal(size=n), 1)  # 取一位小数，制造并列分数
        values[rng.random(n) < 0.1] = np.nan
        alpha = _alpha(values)
        if alpha.notna().sum() < 2 * k:
            continue
        expected = _legacy_top_k_hysteresis(alpha, prev, k, exit_k)
        pd.testing.assert_series_equal(top_k_hysteresis(alpha, prev, k, exit_k), expected)
        prev = expected
