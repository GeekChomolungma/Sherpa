"""向量化 `rank_ic` / `quantile_returns` vs 旧实现（逐行 corrwith / 逐期 qcut）的逐元素对比。

数据里放进缺失、±inf、大量并列、整行恒定、有效样本不足的行。
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import pytest

from sherpa.metrics.factor import quantile_returns, rank_ic


def _legacy_rank_ic(alpha, forward_returns):
    """改动前的实现，原样复制作参考答案。"""
    alpha, forward_returns = alpha.align(forward_returns, join="inner", axis=0)
    common_cols = alpha.columns.intersection(forward_returns.columns)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ic = alpha[common_cols].corrwith(forward_returns[common_cols], axis=1, method="spearman")
    return ic.rename("rank_ic")


def _legacy_quantile_returns(alpha, forward_returns, n_quantiles=10):
    """改动前的实现，原样复制作参考答案。"""
    alpha, forward_returns = alpha.align(forward_returns, join="inner", axis=0)
    common_cols = alpha.columns.intersection(forward_returns.columns)
    a = alpha[common_cols]
    r = forward_returns[common_cols]
    labels = list(range(1, n_quantiles + 1))
    rows: dict = {}
    for t in a.index:
        a_row = a.loc[t]
        r_row = r.loc[t]
        mask = a_row.notna() & r_row.notna()
        if int(mask.sum()) < n_quantiles:
            rows[t] = pd.Series(float("nan"), index=labels)
            continue
        desc_rank = a_row[mask].rank(method="first", ascending=False)
        bucket = pd.qcut(desc_rank, n_quantiles, labels=False) + 1
        rows[t] = r_row[mask].groupby(bucket).mean().reindex(labels)
    return pd.DataFrame.from_dict(rows, orient="index").reindex(columns=labels).sort_index()


def _pair(kind: str, seed: int, rows: int = 50, cols: int = 23):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=rows, freq="4h", tz="UTC")
    columns = [f"S{i}" for i in range(cols)]
    if kind == "ties":
        a = rng.integers(0, 5, size=(rows, cols)).astype(float)
    else:
        a = rng.normal(size=(rows, cols))
    r = 0.3 * a + rng.normal(size=(rows, cols))
    a[rng.random((rows, cols)) < 0.15] = np.nan
    r[rng.random((rows, cols)) < 0.1] = np.nan
    a[3, :] = 1.0  # 整行恒定
    a[7, :-1] = np.nan  # 只剩 1 个有效 symbol
    a[9, :-4] = np.nan  # 只剩 4 个有效 symbol（少于分组数）
    if kind == "inf":
        a[11, 2] = np.inf
        a[13, 5] = -np.inf
    alpha = pd.DataFrame(a, index=index, columns=columns)
    forward = pd.DataFrame(r, index=index, columns=columns)
    return alpha, forward


@pytest.mark.parametrize("kind", ["normal", "ties", "inf"])
@pytest.mark.parametrize("seed", [0, 1, 2])
def test_rank_ic_matches_legacy(kind, seed):
    alpha, forward = _pair(kind, seed)
    expected = _legacy_rank_ic(alpha, forward)
    result = rank_ic(alpha, forward)
    pd.testing.assert_series_equal(result.isna(), expected.isna(), check_names=False)
    np.testing.assert_allclose(result.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)


def test_rank_ic_handles_misaligned_rows_and_columns():
    alpha, forward = _pair("normal", 4)
    forward = forward.iloc[5:].rename(columns={"S0": "OTHER"})  # 行少一截、列不完全重合
    pd.testing.assert_series_equal(rank_ic(alpha, forward), _legacy_rank_ic(alpha, forward), check_exact=False, atol=1e-12)


@pytest.mark.parametrize("kind", ["normal", "ties", "inf"])
@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("n_quantiles", [2, 5, 10])
def test_quantile_returns_matches_legacy(kind, seed, n_quantiles):
    alpha, forward = _pair(kind, seed)
    expected = _legacy_quantile_returns(alpha, forward, n_quantiles)
    result = quantile_returns(alpha, forward, n_quantiles)
    assert list(result.columns) == list(expected.columns)
    assert list(result.index) == list(expected.index)
    # check_freq=False：旧实现用 from_dict 重建表，时间索引丢了 freq 元数据；新实现保留原索引的 freq。
    # 这只是索引上的标签，不是数据，下游不使用。
    pd.testing.assert_frame_equal(result.isna(), expected.isna(), check_names=False, check_freq=False)
    np.testing.assert_allclose(result.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-12, equal_nan=True)
