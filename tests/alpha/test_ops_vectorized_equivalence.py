"""向量化算子 vs 旧实现（`rolling().apply(lambda)`）的逐元素对比。

旧实现原样保留在本文件里作为"参考答案"：向量化只能改变速度，不能改变任何数值。数据里刻意
放进 NaN（整段缺失 + 零星缺失）、±inf、大量并列值（取整后的小整数），覆盖语义最容易出错的地方。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sherpa.alpha import ops


# ---- 旧实现（参考答案，改动前的 sherpa.alpha.ops 原样复制）----

def _legacy_ts_product(x, window):
    return x.rolling(window).apply(lambda s: float(np.prod(s.values)), raw=False)


def _legacy_ts_rank(x, window):
    return x.rolling(window).apply(lambda s: pd.Series(s).rank(pct=True).iloc[-1], raw=False)


def _legacy_ts_argmax(x, window):
    return x.rolling(window).apply(lambda s: float(np.argmax(s.values)), raw=False)


def _legacy_ts_argmin(x, window):
    return x.rolling(window).apply(lambda s: float(np.argmin(s.values)), raw=False)


def _legacy_decay_linear(x, window):
    weights = np.arange(1, window + 1, dtype="float64")
    weights /= weights.sum()
    return x.rolling(window).apply(lambda s: float(np.dot(s.values, weights)), raw=False)


# ---- 测试数据 ----

def _frame(kind: str, seed: int = 0, rows: int = 80, cols: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=rows, freq="4h", tz="UTC")
    columns = [f"S{i}" for i in range(cols)]
    if kind == "ties":
        values = rng.integers(0, 4, size=(rows, cols)).astype(float)  # 大量并列
    else:
        values = rng.normal(size=(rows, cols))
    values[rng.random((rows, cols)) < 0.08] = np.nan  # 零星缺失
    values[:15, 0] = np.nan  # 整段缺失（比如 symbol 晚上线）
    values[40:43, 1] = np.nan  # 中间断档
    if kind == "inf":
        values[20, 2] = np.inf
        values[30, 3] = -np.inf
        values[50, 4] = np.inf
    return pd.DataFrame(values, index=index, columns=columns)


PAIRS = [
    ("ts_product", ops.ts_product, _legacy_ts_product),
    ("ts_rank", ops.ts_rank, _legacy_ts_rank),
    ("ts_argmax", ops.ts_argmax, _legacy_ts_argmax),
    ("ts_argmin", ops.ts_argmin, _legacy_ts_argmin),
    ("decay_linear", ops.decay_linear, _legacy_decay_linear),
]


@pytest.mark.parametrize("name, new, legacy", PAIRS, ids=[p[0] for p in PAIRS])
@pytest.mark.parametrize("kind", ["normal", "ties", "inf"])
@pytest.mark.parametrize("window", [1, 2, 5, 10])
def test_vectorized_matches_legacy(name, new, legacy, kind, window):
    x = _frame(kind, seed=window)
    expected = legacy(x, window)
    result = new(x, window)
    # 必须逐位相同，不接受"浮点舍入级别"的差异：下游常接截面 rank()，末位差异也会把精确并列的值
    # 拆开、让名次变一档（点积换成 matmul 时就实测改变了 4 个世坤因子的输出）。
    pd.testing.assert_frame_equal(result, expected, check_exact=True)


@pytest.mark.parametrize("name, new, legacy", PAIRS, ids=[p[0] for p in PAIRS])
def test_window_longer_than_history_is_all_nan(name, new, legacy):
    x = _frame("normal", rows=5)
    pd.testing.assert_frame_equal(new(x, 10), legacy(x, 10))


@pytest.mark.parametrize("name, new, legacy", PAIRS, ids=[p[0] for p in PAIRS])
def test_chunking_does_not_change_results(name, new, legacy, monkeypatch):
    # 把分块上限压到很小，强制分成很多块，结果应该和不分块完全一样。
    x = _frame("normal", seed=7, rows=60)
    whole = new(x, 6)
    monkeypatch.setattr(ops, "_WINDOW_CHUNK_ELEMENTS", 50)
    pd.testing.assert_frame_equal(new(x, 6), whole)


def test_rejects_non_positive_window():
    with pytest.raises(ValueError):
        ops.ts_rank(_frame("normal"), 0)
