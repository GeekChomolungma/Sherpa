import numpy as np
import pandas as pd

from sherpa.backtest.alpha_check import run_alpha_check


def _synthetic_panel(n_periods, n_symbols, seed):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n_periods, freq="1min", tz="UTC")
    columns = [f"SYM{i}" for i in range(n_symbols)]
    return rng, index, columns


def test_run_alpha_check_passes_for_strong_stable_factor():
    # 噪声小到 IC 每期都约等于 1.0，std~=0、IC_IR 是 +inf 的边界情形——这个用例同时验证
    # "完美因子"不会被 §8.4.1 的 IC_IR 阈值判定误判成不通过（见 metrics.factor.ic_summary）。
    rng, index, columns = _synthetic_panel(n_periods=40, n_symbols=12, seed=0)
    base = np.tile(np.arange(len(columns), dtype=float), (len(index), 1))
    alpha = pd.DataFrame(base, index=index, columns=columns)
    noise = rng.normal(0, 0.001, size=base.shape)
    forward_returns = pd.DataFrame(base * 0.01 + noise, index=index, columns=columns)

    result = run_alpha_check(alpha, forward_returns, n_quantiles=4, ic_ir_threshold=0.5)

    assert result.ic_mean > 0.5
    assert result.passed is True
    assert list(result.quantile_returns.columns) == [1, 2, 3, 4]
    assert len(result.ic_series) == len(index)


def test_run_alpha_check_fails_for_pure_noise():
    rng, index, columns = _synthetic_panel(n_periods=40, n_symbols=12, seed=1)
    alpha = pd.DataFrame(rng.normal(size=(len(index), len(columns))), index=index, columns=columns)
    forward_returns = pd.DataFrame(rng.normal(size=(len(index), len(columns))), index=index, columns=columns)

    result = run_alpha_check(alpha, forward_returns, n_quantiles=4, ic_ir_threshold=0.5)

    assert result.passed is False


def test_run_alpha_check_ic_ir_threshold_is_configurable():
    # 噪声比"完美因子"那个用例大一档，让 IC_IR 是个有限值（而不是 inf），这样才能真的用
    # 一个足够高的阈值把它判不过。
    rng, index, columns = _synthetic_panel(n_periods=40, n_symbols=12, seed=0)
    base = np.tile(np.arange(len(columns), dtype=float), (len(index), 1))
    alpha = pd.DataFrame(base, index=index, columns=columns)
    noise = rng.normal(0, 0.01, size=base.shape)
    forward_returns = pd.DataFrame(base * 0.01 + noise, index=index, columns=columns)

    lenient = run_alpha_check(alpha, forward_returns, ic_ir_threshold=0.01)
    strict = run_alpha_check(alpha, forward_returns, ic_ir_threshold=1000.0)

    assert lenient.passed is True
    assert strict.passed is False
