"""无状态算子库：世坤 101 风格的横截面/时序算子（设计文档第 6 章）。

所有函数的输入输出都是 (T, N) 的 pandas.DataFrame（行=start_time, 列=symbol），
跟 BarPanel 的某个字段（如 panel.close）形状/index/columns完全一致；函数本身不知道
BarPanel/Alpha 类的存在——这是"指标函数只依赖内存结构"这条硬性原则（设计文档 5.1）
在算子层的体现，也是它们能被 pandas 向量化、可以脱离 Alpha 框架单独测试的原因。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---- 横截面算子：按行操作，跨 symbol ----


def rank(x: pd.DataFrame) -> pd.DataFrame:
    """横截面百分位排名，每行（每个时间戳）内单独排，值域 (0, 1]。"""
    return x.rank(axis=1, pct=True)


def scale(x: pd.DataFrame, target_sum: float = 1.0) -> pd.DataFrame:
    """把每行按绝对值之和归一化到 target_sum（世坤101里常用来把因子值转成可直接当仓位权重的形式）。"""
    denom = x.abs().sum(axis=1)
    return x.div(denom, axis=0) * target_sum


def indneutralize(x: pd.DataFrame, industry: pd.Series | None = None) -> pd.DataFrame:
    """世坤101里的行业中性化算子。

    当前 BarPanel 没有行业分类字段（crypto 永续市场没有天然的"行业"维度），
    依赖这个算子的公式在 v1 里不实现——不要为了"能跑"就拿一个凑出来的代理维度
    （比如随便按上线时间分组）硬套，那样产出的因子值没有经济含义，反而有害。
    见设计文档 §6.3、sherpa.alpha.worldquant.cross_sectional。
    """
    raise NotImplementedError("indneutralize 需要行业分类数据，当前 BarPanel 不支持（设计文档 §6.3）")


# ---- 时序算子：按列操作，逐 symbol 独立沿时间轴滚动 ----


def delay(x: pd.DataFrame, periods: int) -> pd.DataFrame:
    return x.shift(periods)


def delta(x: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    return x.diff(periods)


def ts_sum(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).sum()


def ts_min(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).min()


def ts_max(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).max()


def stddev(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).std()


def ts_product(x: pd.DataFrame, window: int) -> pd.DataFrame:
    """窗口内累乘（世坤101公式里的 `product(x, d)`）。"""
    return x.rolling(window).apply(lambda s: float(np.prod(s.values)), raw=False)


def ts_rank(x: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动窗口内的时序百分位排名（逐 symbol 独立，不跨 symbol，别跟 rank() 搞混）。"""
    return x.rolling(window).apply(lambda s: pd.Series(s).rank(pct=True).iloc[-1], raw=False)


def ts_argmax(x: pd.DataFrame, window: int) -> pd.DataFrame:
    """窗口内最大值出现的位置：0 = 窗口最早一根，window-1 = 当前这一根。"""
    return x.rolling(window).apply(lambda s: float(np.argmax(s.values)), raw=False)


def ts_argmin(x: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).apply(lambda s: float(np.argmin(s.values)), raw=False)


def ts_corr(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    """滚动皮尔逊相关系数。窗口内方差趋近于 0 时（比如横截面 rank 在只有几个 symbol 的
    小市场里连续几期打平），浮点误差会让"本该恰好是 0"的方差算成 ~1e-17 而不是精确 0，
    分母趋近 0 但不精确为 0——这会让 pandas 算出 `inf`，甚至是 `1.5` 这种超出 [-1,1] 定义域
    但看着又不像 inf 的"貌似正常"的错误值（同一个数值不稳定问题的两种外在表现）。这个坑
    已经在 `sherpa.metrics.factor.ic_summary`/`sherpa.metrics.performance.sharpe_ratio`
    踩过两次，这里统一处理：明显越界（超过定义域 1e-6 以上）的判定为数值不稳定，收口成
    NaN；只是浮点舍入级别的轻微越界（比如 1.0000000002）夹回 [-1,1]，不当作错误。
    """
    result = x.rolling(window).corr(y)
    result = result.where(result.abs() <= 1 + 1e-6)
    return result.clip(lower=-1.0, upper=1.0)


def ts_cov(x: pd.DataFrame, y: pd.DataFrame, window: int) -> pd.DataFrame:
    return x.rolling(window).cov(y)


def decay_linear(x: pd.DataFrame, window: int) -> pd.DataFrame:
    """线性衰减加权移动平均：离当前越近的数据权重越大，权重线性递增后归一化。"""
    weights = np.arange(1, window + 1, dtype="float64")
    weights /= weights.sum()
    return x.rolling(window).apply(lambda s: float(np.dot(s.values, weights)), raw=False)


# ---- 逐元素算子 ----


def signed_power(x: pd.DataFrame, power: float | pd.DataFrame) -> pd.DataFrame:
    """保持符号的幂：`sign(x) * |x|^power`。`power` 也可以是逐元素变化的 DataFrame
    （世坤101 Alpha#84 就是这么用的：指数本身是 `delta(close, 4)`，不是常数）。"""
    return np.sign(x) * (x.abs() ** power)


def sign(x: pd.DataFrame) -> pd.DataFrame:
    return np.sign(x)


def log(x: pd.DataFrame) -> pd.DataFrame:
    return np.log(x)


# ---- 常见子表达式的便捷封装（世坤101公式里反复出现）----


def adv(volume: pd.DataFrame, window: int) -> pd.DataFrame:
    """average daily volume：世坤101公式里常见的 adv{N} 子表达式。"""
    return volume.rolling(window).mean()


def vwap(quote_volume: pd.DataFrame, volume: pd.DataFrame) -> pd.DataFrame:
    """用 quote_volume/volume 近似K线内的成交量加权均价——BarPanel 没有原生 vwap 字段。"""
    return quote_volume / volume
