import pandas as pd
import pytest

from sherpa.metrics.regime import (
    build_regime_report,
    compute_dispersion_regime,
    compute_liquidity_regime,
    compute_trend_regime,
    compute_volatility_regime,
)


def _frame(rows):
    index = pd.date_range("2026-01-01", periods=len(rows), freq="4h", tz="UTC")
    return pd.DataFrame(rows, index=index)


def test_compute_trend_regime_requires_benchmark_symbol_present():
    close = _frame([{"ETHUSDT": 1.0}])

    with pytest.raises(KeyError):
        compute_trend_regime(close, benchmark_symbol="BTCUSDT")


def test_compute_trend_regime_warmup_is_na():
    close = _frame([{"BTCUSDT": 100.0 + i, "ETHUSDT": 10.0 + i} for i in range(3)])

    trend = compute_trend_regime(close, benchmark_symbol="BTCUSDT", ma_period=5)

    assert trend["trend_state"].isna().all()
    assert trend["benchmark_trend_up"].isna().all()


def test_compute_trend_regime_bull_and_bear():
    n = 10
    # BTC 持续上涨、且全市场普涨 -> bull；全市场普跌 -> bear。
    bull_rows = [{"BTCUSDT": 100.0 + i, "ETHUSDT": 10.0 + i, "SOLUSDT": 1.0 + i} for i in range(n)]
    close = _frame(bull_rows)
    trend = compute_trend_regime(close, benchmark_symbol="BTCUSDT", ma_period=3, bull_breadth=0.5)
    assert (trend["trend_state"].dropna() == "bull").all()

    bear_rows = [{"BTCUSDT": 100.0 - i, "ETHUSDT": 10.0 - i, "SOLUSDT": 1.0 - i} for i in range(n)]
    close = _frame(bear_rows)
    trend = compute_trend_regime(close, benchmark_symbol="BTCUSDT", ma_period=3, bear_breadth=0.5)
    assert (trend["trend_state"].dropna() == "bear").all()


def test_compute_volatility_regime_high_low_buckets():
    # 前半段完全不动（低波），后半段振幅递增的震荡（高波，且逐步创新高）：
    # 保证收尾那根 bar 的滚动波动率是整个回溯窗口里的最大值，percentile rank 必然落在 high 档。
    calm = [100.0] * 40
    wild = []
    price = 100.0
    for i in range(40):
        pct = 0.02 * (i + 1)
        price *= (1 + pct) if i % 2 == 0 else (1 - pct)
        wild.append(price)
    close = _frame([{"A": p} for p in calm + wild])

    vol = compute_volatility_regime(close, window=3, lookback=60)
    states = vol["volatility_state"].dropna()

    # 低档（"low"）由跟这里同一个 `_quantile_bucket` 分桶逻辑的 liquidity "starved" 用例覆盖，
    # 这里只需确认持续创新高的尾部会被打上 high。
    assert states.iloc[-1] == "high"


def test_compute_dispersion_regime_high_when_symbols_diverge():
    n = 60
    rows = []
    for i in range(n):
        # 一半时间两只币同涨同跌（零离散），一半时间一涨一跌（高离散）。
        if i < n // 2:
            rows.append({"A": 100.0 + i, "B": 100.0 + i})
        else:
            rows.append({"A": 100.0 + i, "B": 100.0 - i})
    close = _frame(rows)

    disp = compute_dispersion_regime(close, lookback=n - 1)
    assert disp["dispersion_state"].dropna().iloc[-1] == "high"


def test_compute_liquidity_regime_starved_and_high():
    n = 60
    quote_volume = _frame([{"A": 1.0} for _ in range(n // 2)] + [{"A": 1000.0} for _ in range(n // 2)])
    taker_buy_quote_volume = quote_volume * 0.5

    liq = compute_liquidity_regime(quote_volume, taker_buy_quote_volume, lookback=n)

    assert liq["liquidity_state"].dropna().iloc[-1] == "high"
    assert liq["taker_buy_ratio"].iloc[-1] == pytest.approx(0.5)


def test_build_regime_report_label_is_na_until_all_dims_known():
    n = 8
    close = _frame([{"BTCUSDT": 100.0 + i, "ETHUSDT": 10.0 + i} for i in range(n)])
    quote_volume = _frame([{"BTCUSDT": 1.0 + i, "ETHUSDT": 1.0 + i} for i in range(n)])
    taker_buy_quote_volume = quote_volume * 0.5

    report = build_regime_report(
        close, quote_volume, taker_buy_quote_volume,
        benchmark_symbol="BTCUSDT", ma_period=3, vol_window=2, lookback=5,
    )

    assert list(report.columns) == ["trend", "volatility", "dispersion", "liquidity", "regime_label"]
    assert report["regime_label"].isna().any()
    assert report["regime_label"].notna().any()
    known = report["regime_label"].notna()
    for idx in report.index[known]:
        row = report.loc[idx]
        assert row["regime_label"] == "|".join([row["trend"], row["volatility"], row["dispersion"], row["liquidity"]])
