"""测试用的合成 BarPanel，不依赖真实 ClickHouse/Redis 数据。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel, build_coverage


def make_panel(n: int = 40, symbols=("BTCUSDT", "ETHUSDT", "SOLUSDT"), seed: int = 0) -> BarPanel:
    """随机但自洽的 OHLCV 面板：high>=max(open,close), low<=min(open,close)，够长可以跑完 Alpha001 的25根warmup。"""
    rng = np.random.default_rng(seed)
    symbols = list(symbols)
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC", name="start_time")

    close = pd.DataFrame(
        100 + np.cumsum(rng.normal(0, 1, size=(n, len(symbols))), axis=0),
        index=index,
        columns=symbols,
    )
    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0] - rng.normal(0, 1, size=len(symbols))

    hi_noise = rng.uniform(0.1, 1.0, size=(n, len(symbols)))
    lo_noise = rng.uniform(0.1, 1.0, size=(n, len(symbols)))
    high = pd.DataFrame(np.maximum(open_.values, close.values), index=index, columns=symbols) + hi_noise
    low = pd.DataFrame(np.minimum(open_.values, close.values), index=index, columns=symbols) - lo_noise

    volume = pd.DataFrame(rng.uniform(100, 1000, size=(n, len(symbols))), index=index, columns=symbols)
    quote_volume = volume * close
    taker_buy_volume = volume * rng.uniform(0.3, 0.7, size=(n, len(symbols)))
    taker_buy_quote_volume = taker_buy_volume * close
    trades_count = pd.DataFrame(
        rng.integers(10, 100, size=(n, len(symbols))).astype("float64"), index=index, columns=symbols
    )

    fields = dict(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quote_volume=quote_volume,
        taker_buy_volume=taker_buy_volume,
        taker_buy_quote_volume=taker_buy_quote_volume,
        trades_count=trades_count,
    )
    coverage = build_coverage(close, universe_size=len(symbols))
    return BarPanel(interval="1m", symbols=tuple(symbols), coverage=coverage, **fields)


def make_single_symbol_panel(closes, highs=None, lows=None, opens=None, volumes=None, symbol="BTCUSDT") -> BarPanel:
    """单 symbol、手工指定数值的面板，用来对因子做精确数值验证。"""
    n = len(closes)
    index = pd.date_range("2026-01-01", periods=n, freq="1min", tz="UTC", name="start_time")
    close = pd.DataFrame({symbol: closes}, index=index, dtype="float64")
    opens = opens if opens is not None else [closes[0]] + list(closes[:-1])
    open_ = pd.DataFrame({symbol: opens}, index=index, dtype="float64")
    high = pd.DataFrame({symbol: highs if highs is not None else [c + 1 for c in closes]}, index=index, dtype="float64")
    low = pd.DataFrame({symbol: lows if lows is not None else [c - 1 for c in closes]}, index=index, dtype="float64")
    volume = pd.DataFrame({symbol: volumes if volumes is not None else [500.0] * n}, index=index, dtype="float64")
    quote_volume = volume * close
    taker_buy_volume = volume * 0.5
    taker_buy_quote_volume = taker_buy_volume * close
    trades_count = pd.DataFrame({symbol: [10.0] * n}, index=index)

    fields = dict(
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        quote_volume=quote_volume,
        taker_buy_volume=taker_buy_volume,
        taker_buy_quote_volume=taker_buy_quote_volume,
        trades_count=trades_count,
    )
    coverage = build_coverage(close, universe_size=1)
    return BarPanel(interval="1m", symbols=(symbol,), coverage=coverage, **fields)
