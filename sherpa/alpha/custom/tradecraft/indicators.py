"""tradecraft alpha 共用的指标：`BarPanel` → `(T, N)` 原始值，**不排名、不盖范围**。

交易规则里经常要用原始值（"一天涨超 5%"、"OI 一天涨 20%"），所以这里都给原始值；需要截面比较时在 alpha 里用
`TradecraftAlpha.rank_in_scope`。全部只用到 t 为止的数据（rolling / pct_change），不会看未来。

公式跟 ML 特征（`sherpa/alpha/custom/ml/features.py`）里验证过的写法一致，但**故意不 import 它**：ML 特征进了模型
指纹、而且都做过截面排名，两边绑在一起会互相牵制。新指标先加在这里，确实被多个 alpha 用到才值得放进来。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel


def _safe_div(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """除数为 0 时给 NaN（不是 inf）。"""
    return a / b.where(b != 0)


def _require(panel: BarPanel, field: str) -> pd.DataFrame:
    value = getattr(panel, field)
    if value is None:
        raise ValueError(f"面板没有 {field}（取数时没带上，或 1m 周期没有这个字段）")
    return value


# ---- 价格 ----

def returns(panel: BarPanel, bars: int) -> pd.DataFrame:
    """最近 `bars` 根的涨跌幅：close_t / close_{t−bars} − 1。"""
    return panel.close.pct_change(bars, fill_method=None)


def realized_vol(panel: BarPanel, bars: int) -> pd.DataFrame:
    """最近 `bars` 根逐根收益的标准差（不年化）。"""
    return panel.close.pct_change(fill_method=None).rolling(bars).std()


def range_position(panel: BarPanel, bars: int) -> pd.DataFrame:
    """收盘价在最近 `bars` 根高低点区间里的位置：0 = 区间最低，1 = 区间最高。区间宽度为 0 时 NaN。"""
    high = panel.high.rolling(bars).max()
    low = panel.low.rolling(bars).min()
    return _safe_div(panel.close - low, high - low)


def dist_from_high(panel: BarPanel, bars: int) -> pd.DataFrame:
    """收盘价 / 最近 `bars` 根最高价 − 1，<= 0，越接近 0 越靠近高点。"""
    return _safe_div(panel.close, panel.high.rolling(bars).max()) - 1


def dist_from_low(panel: BarPanel, bars: int) -> pd.DataFrame:
    """收盘价 / 最近 `bars` 根最低价 − 1，>= 0，越接近 0 越靠近低点。"""
    return _safe_div(panel.close, panel.low.rolling(bars).min()) - 1


def candle_body_ratio(panel: BarPanel) -> pd.DataFrame:
    """当根 K 线实体占振幅的比例，−1（光头光脚阴线）~ 1（光头光脚阳线）。振幅为 0 时 NaN。"""
    return _safe_div(panel.close - panel.open, panel.high - panel.low)


def upper_shadow_ratio(panel: BarPanel) -> pd.DataFrame:
    """当根 K 线上影线占振幅的比例，0 ~ 1：越大 = 冲高后被打回来越多（上方抛压）。振幅为 0 时 NaN。"""
    body_top = panel.open.where(panel.open > panel.close, panel.close)
    return _safe_div(panel.high - body_top, panel.high - panel.low)


def return_acceleration(panel: BarPanel, bars: int) -> pd.DataFrame:
    """涨幅的变化率：最近 `bars` 根的平均逐根收益 − 再往前 `bars` 根的平均逐根收益。
    > 0 = 涨得越来越快（加速）；< 0 = 涨幅在缩小（减速 / 衰竭）。"""
    r = panel.close.pct_change(fill_method=None)
    recent = r.rolling(bars).mean()
    return recent - recent.shift(bars)


def efficiency_ratio(close: pd.Series | pd.DataFrame, bars: int) -> pd.Series | pd.DataFrame:
    """趋势效率：最近 `bars` 根的净涨跌幅度 / 逐根涨跌幅度之和，0 ~ 1。
    接近 1 = 一路单边；接近 0 = 来回震荡、走了很多路但净位移很小（横盘 / 频繁震荡）。"""
    net = (close - close.shift(bars)).abs()
    path = close.diff().abs().rolling(bars).sum()
    return net / path.where(path != 0)


# ---- 成交 ----

def quote_volume_mean(panel: BarPanel, bars: int) -> pd.DataFrame:
    """最近 `bars` 根平均成交额（USDT）。"""
    return panel.quote_volume.rolling(bars).mean()


def volume_surge(panel: BarPanel, short: int, long: int) -> pd.DataFrame:
    """放量倍数：最近 `short` 根平均成交额 / 最近 `long` 根平均成交额，> 1 = 放量。"""
    return _safe_div(panel.quote_volume.rolling(short).mean(), panel.quote_volume.rolling(long).mean())


def taker_buy_ratio(panel: BarPanel, bars: int) -> pd.DataFrame:
    """最近 `bars` 根主动买入成交额 / 总成交额，> 0.5 = 买盘更主动。"""
    return _safe_div(panel.taker_buy_quote_volume.rolling(bars).sum(), panel.quote_volume.rolling(bars).sum())


# ---- 合约持仓 / 多空比（面板没取这些字段时报错，不悄悄给 NaN）----

def oi_change(panel: BarPanel, bars: int) -> pd.DataFrame:
    """最近 `bars` 根未平仓量（OI）的变化率。"""
    return _require(panel, "open_interest").pct_change(bars, fill_method=None)


def oi_value(panel: BarPanel) -> pd.DataFrame:
    """未平仓合约价值（OI × 收盘价，USDT）。"""
    return _require(panel, "open_interest") * panel.close


def long_short_zscore(panel: BarPanel, bars: int, field: str = "long_short_ratio") -> pd.DataFrame:
    """多空比相对最近 `bars` 根的 z 分数：> 0 = 多头比平时更拥挤。`field` 可换成 top_account / top_position 的多空比。"""
    ratio = _require(panel, field)
    mean = ratio.rolling(bars).mean()
    std = ratio.rolling(bars).std()
    return _safe_div(ratio - mean, std)


def log_or_nan(x: pd.DataFrame) -> pd.DataFrame:
    """非正值给 NaN 再取对数（成交额、OI 价值这类跨币量级差很多的量，比较前先取对数）。"""
    return np.log(x.where(x > 0))
