"""向量化 `neutralize` vs 旧实现（逐期 `np.linalg.lstsq`）的逐元素对比。

两者是不同的求解算法（批量正规方程 + 伪逆 vs 逐期 SVD），不可能逐位相同；要求 NaN 位置完全一致、
数值差异在 1e-10 以内。数据里放进缺失、±inf、有效样本不足的期、以及某期暴露在截面上恰好为常数（共线）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from sherpa.risk.neutralize import neutralize


def _legacy_neutralize(raw_score, exposures):
    """改动前的实现，原样复制作参考答案。"""
    exposure_names = list(exposures.keys())
    min_valid = len(exposure_names) + 2
    residual = pd.DataFrame(float("nan"), index=raw_score.index, columns=raw_score.columns)
    for t in raw_score.index:
        columns = {"__score__": raw_score.loc[t]}
        for name in exposure_names:
            columns[name] = exposures[name].loc[t]
        frame = pd.DataFrame(columns).replace([np.inf, -np.inf], np.nan).dropna()
        if len(frame) < min_valid:
            continue
        design = np.column_stack([np.ones(len(frame))] + [frame[name].to_numpy() for name in exposure_names])
        target = frame["__score__"].to_numpy()
        try:
            coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
        except np.linalg.LinAlgError:
            continue
        residual.loc[t, frame.index] = target - design @ coefficients
    return residual


def _data(seed: int, rows: int = 60, cols: int = 30, n_exposures: int = 2):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=rows, freq="4h", tz="UTC")
    columns = [f"S{i}" for i in range(cols)]
    score = rng.normal(size=(rows, cols))
    score[rng.random((rows, cols)) < 0.2] = np.nan  # 类似流动性掩码
    score[5, :cols - 2] = np.nan  # 这一期有效样本不足
    exposures = {}
    for k in range(n_exposures):
        values = rng.normal(size=(rows, cols)) * (k + 1) + (10.0 if k == 1 else 0.0)  # Size 代理量级约 10
        values[rng.random((rows, cols)) < 0.05] = np.nan
        values[12, 3] = -np.inf  # log(0)
        values[20, :] = 7.0 if k == 0 else values[20, :]  # 这一期第一个暴露在截面上是常数（共线）
        exposures[f"e{k}"] = pd.DataFrame(values, index=index, columns=columns)
    return pd.DataFrame(score, index=index, columns=columns), exposures


@pytest.mark.parametrize("seed", [0, 1, 2])
@pytest.mark.parametrize("n_exposures", [1, 2, 3])
def test_vectorized_neutralize_matches_legacy(seed, n_exposures):
    score, exposures = _data(seed, n_exposures=n_exposures)
    expected = _legacy_neutralize(score, exposures)
    result = neutralize(score, exposures)
    pd.testing.assert_frame_equal(result.isna(), expected.isna())
    np.testing.assert_allclose(result.to_numpy(), expected.to_numpy(), rtol=0, atol=1e-10, equal_nan=True)


def test_chunking_does_not_change_results(monkeypatch):
    from sherpa.risk import neutralize as module

    score, exposures = _data(3)
    whole = neutralize(score, exposures)
    monkeypatch.setattr(module, "_ROW_CHUNK", 7)
    pd.testing.assert_frame_equal(neutralize(score, exposures), whole)


def test_constant_cross_section_gives_exact_zero_residual_and_nan_ic():
    """有意与旧实现不同的一处：某期分数在截面上完全相同（没有排序信息）时，残差精确为 0，IC 为 NaN。

    旧实现逐期 lstsq 会留下 1e-16 量级的舍入噪声，rank_ic 对噪声排名后算出一个纯随机的"有效" IC
    （实测：alpha042 在当前实现下恒等于 1，旧流程却给它算出了 IC）。这里锁定正确行为。
    """
    from sherpa.metrics.factor import rank_ic

    score, exposures = _data(5)
    score.iloc[10] = 0.1  # 0.1 这类值多个求平均不能精确还原，专门用来检验"不靠浮点运气"
    score.iloc[11] = 1.0
    residual = neutralize(score, exposures)
    for row in (10, 11):
        values = residual.iloc[row].dropna()
        assert len(values) > 0 and (values == 0.0).all()

    forward = score * 0 + np.random.default_rng(0).normal(size=score.shape)
    ic = rank_ic(residual, forward)
    assert np.isnan(ic.iloc[10]) and np.isnan(ic.iloc[11])
