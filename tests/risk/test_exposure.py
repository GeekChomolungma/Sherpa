import numpy as np
import pandas as pd
import pytest

from sherpa.risk.exposure import rolling_beta


def _frame(rows, columns):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="1h", tz="UTC")
    return pd.DataFrame(rows, index=index, columns=columns)


def test_rolling_beta_recovers_known_linear_relationship():
    # BENCH 自己走一条已知路径；HIGH 每步都是 BENCH 的 2 倍，LOW 是 0.5 倍——
    # 滚动 beta 应该分别收敛到 ~2.0 和 ~0.5。
    rng = np.random.default_rng(0)
    bench_returns = rng.normal(0, 0.01, size=200)
    bench_price = 100 * np.cumprod(1 + bench_returns)
    high_price = 100 * np.cumprod(1 + 2.0 * bench_returns)
    low_price = 100 * np.cumprod(1 + 0.5 * bench_returns)

    close = _frame(
        list(zip(bench_price, high_price, low_price)),
        ["BENCH", "HIGH", "LOW"],
    )

    beta = rolling_beta(close, benchmark_symbol="BENCH", window=60)

    assert beta["HIGH"].iloc[-1] == pytest.approx(2.0, abs=0.05)
    assert beta["LOW"].iloc[-1] == pytest.approx(0.5, abs=0.05)
    assert beta["BENCH"].iloc[-1] == pytest.approx(1.0, abs=1e-6)


def test_rolling_beta_warmup_is_nan():
    columns = ["BENCH", "A"]
    n = 10
    close = _frame([[100.0 + i, 50.0 + i] for i in range(n)], columns)

    beta = rolling_beta(close, benchmark_symbol="BENCH", window=20)

    assert beta.isna().all().all()


def test_rolling_beta_missing_benchmark_raises():
    close = _frame([[100.0, 50.0]] * 5, ["A", "B"])

    with pytest.raises(KeyError):
        rolling_beta(close, benchmark_symbol="BTCUSDT", window=3)


def test_rolling_beta_zero_variance_window_is_nan_not_inf():
    # BENCH 在窗口内完全走平（收益率恒为 0），方差为 0——除法不该产出 inf/巨大值。
    columns = ["BENCH", "A"]
    n = 30
    bench_price = [100.0] * n
    a_price = [50.0 + i for i in range(n)]
    close = _frame(list(zip(bench_price, a_price)), columns)

    beta = rolling_beta(close, benchmark_symbol="BENCH", window=10)

    tail = beta["A"].iloc[-5:]
    assert tail.isna().all()
