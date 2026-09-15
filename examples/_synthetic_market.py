"""两个 example 共用的合成行情数据生成器。

不连接真实 ClickHouse/Redis——生成的价格路径给每个 symbol 一个持续不变的"潜在收益率"
`mu_i`，这样"过去 N 根的累计收益"这类动量因子在这份数据上才有真实、可复现的预测力，
example 才能演示"一个真正有效的信号该长什么样"，而不是在纯噪声上自娱自乐。

真实市场不存在这种恒定不变的 alpha 分数，这里的信噪比也远高于真实市场——这是刻意调出来
的教学参数，让示例代码跑起来的数字"看着 work"，不代表这套参数在真实数据上会有同样表现。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.normalizer import CH_LONG_FORM_COLUMNS
from sherpa.data.schema import PANEL_FIELDS, BarPanel, build_coverage

_FREQ_BY_INTERVAL = {"1m": "1min", "5m": "5min", "15m": "15min", "1h": "1h", "4h": "4h", "1d": "1D"}


def make_synthetic_ohlcv(
    *,
    n_symbols: int = 10,
    n_bars: int = 500,
    mu_spread: float = 0.004,
    noise_std: float = 0.01,
    seed: int = 0,
    interval: str = "1m",
) -> tuple[pd.DataFrame, dict[str, float]]:
    """生成一份 (close 宽表, {symbol: mu}）。

    `mu` 是每根 bar 的期望收益率，跨 symbol 不同、且不随时间变化，模拟"个别标的持续
    跑赢/跑输大盘"的场景——一个用"过去收益"预测"未来收益"的动量因子，本质上就是在
    估计这个 `mu`。
    """
    rng = np.random.default_rng(seed)
    symbols = [f"SYM{i}" for i in range(n_symbols)]
    mus = rng.normal(0.0, mu_spread, size=n_symbols)
    index = pd.date_range("2026-01-01", periods=n_bars, freq=_FREQ_BY_INTERVAL[interval], tz="UTC", name="start_time")

    per_bar_returns = mus[None, :] + rng.normal(0.0, noise_std, size=(n_bars, n_symbols))
    close = 100.0 * np.cumprod(1.0 + per_bar_returns, axis=0)
    close_df = pd.DataFrame(close, index=index, columns=symbols)
    return close_df, dict(zip(symbols, mus))


def close_to_panel(close: pd.DataFrame, interval: str = "1m") -> BarPanel:
    """只用 close 填满 BarPanel 的全部 9 个字段——example 只关心价格，不需要真实的
    OHLC/成交量关系。

    只适合"只看收盘价动量"的因子（比如 vectorized_research.py/runner_backtest_with_stop_loss.py
    里那个 `close.pct_change(N)`）——这么填会让 `vwap = quote_volume/volume` 退化成常数 1.0
    （分子分母都是同一份 close 拷贝），任何看 vwap/成交量的因子在这份数据上都会失真。批量
    评估世坤101这种会用到全部字段的场景，要用下面的 `make_full_synthetic_panel`。
    """
    symbols = tuple(close.columns)
    fields = {name: close.copy() for name in PANEL_FIELDS if name != "close"}
    coverage = build_coverage(close, universe_size=len(symbols))
    return BarPanel(interval=interval, symbols=symbols, coverage=coverage, close=close, **fields)


def make_full_synthetic_panel(
    *,
    n_symbols: int = 20,
    n_bars: int = 400,
    mu_spread: float = 0.004,
    noise_std: float = 0.01,
    seed: int = 0,
    interval: str = "1m",
) -> BarPanel:
    """跟 `close_to_panel` 不同，这个版本把 `BarPanel` 的全部 9 个字段都造成互相独立、
    有真实变化的样子：open/high/low 有振幅，volume 独立随机，vwap 跟 close 之间有一点点
    价差（不是精确相等）——批量筛选像世坤101这种会用到 open/high/low/volume/vwap 的因子库
    时，需要这些字段真的能变化，不能像 `close_to_panel` 那样全部复制同一份 close。
    """
    close, _mus = make_synthetic_ohlcv(
        n_symbols=n_symbols, n_bars=n_bars, mu_spread=mu_spread, noise_std=noise_std, seed=seed, interval=interval
    )
    rng = np.random.default_rng(seed + 1)  # 独立随机流，不跟生成 close 的那个共用状态
    symbols = list(close.columns)
    index = close.index
    shape = close.shape

    open_ = close.shift(1)
    open_.iloc[0] = close.iloc[0]

    intrabar_range = close.abs().to_numpy() * rng.uniform(0.001, 0.01, size=shape)
    high = pd.DataFrame(np.maximum(open_.to_numpy(), close.to_numpy()) + intrabar_range, index=index, columns=symbols)
    low = pd.DataFrame(np.minimum(open_.to_numpy(), close.to_numpy()) - intrabar_range, index=index, columns=symbols)

    volume = pd.DataFrame(rng.uniform(100.0, 1000.0, size=shape), index=index, columns=symbols)
    vwap_drift = close.to_numpy() * (1.0 + rng.normal(0.0, 0.0005, size=shape))
    quote_volume = pd.DataFrame(volume.to_numpy() * vwap_drift, index=index, columns=symbols)
    taker_ratio = rng.uniform(0.3, 0.7, size=shape)
    taker_buy_volume = volume * taker_ratio
    taker_buy_quote_volume = quote_volume * taker_ratio
    trades_count = pd.DataFrame(rng.integers(10, 500, size=shape).astype("float64"), index=index, columns=symbols)

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
    return BarPanel(interval=interval, symbols=tuple(symbols), coverage=coverage, **fields)


def close_to_ch_long_df(close: pd.DataFrame) -> pd.DataFrame:
    """把 close 宽表转成 `CHReader.fetch_history()` 会返回的长表格式，喂给下面的假客户端。"""
    rows = []
    for symbol in close.columns:
        frame = pd.DataFrame({"start_time": close.index, "symbol": symbol})
        for field in PANEL_FIELDS:
            frame[field] = close[symbol].to_numpy()
        rows.append(frame)
    long_df = pd.concat(rows, ignore_index=True)
    return long_df[list(CH_LONG_FORM_COLUMNS)]


class FakeClickHouseClient:
    """只满足 `sherpa.data.ch_reader.ClickHouseClient` Protocol（`query_df(sql)`）的假客户端。

    按 SQL 文本的特征分发到两种预置响应——`CHReader.fetch_history()` 的主查询，和
    `CHReader.get_listing_times()` 的 `min(start_time)` 查询（`Universe.as_of()` 会用到
    后者）。真实环境把它换成 `clickhouse_connect.get_client(...)` 即可，`CHReader`/
    `Universe`/`HistoricalPanelSource` 这些上层代码不需要改一行。
    """

    def __init__(self, long_df: pd.DataFrame):
        self._long_df = long_df

    def query_df(self, sql: str) -> pd.DataFrame:
        if "min(start_time)" in sql:
            listed_at = self._long_df.groupby("symbol")["start_time"].min().reset_index()
            listed_at.columns = ["symbol", "listed_at"]
            return listed_at
        return self._long_df.copy()
