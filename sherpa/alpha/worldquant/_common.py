"""世坤101公式翻译时反复用到的几个小工具，收口一次，不在每个文件里各写一份。

背景（设计文档 §6.5 已经踩过的坑）：pandas/numpy 里 `NaN > 0` 直接算 `False`，不是 `NaN`，
所以任何"用布尔比较模拟三元表达式/直接把布尔值当分数"的公式，warmup 阶段如果不显式拿
原始输入的 `notna()` 重新盖一遍，会冒出"看起来正常但没有意义"的 0/1/-1，而不是老实的 NaN。

另一个背景（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` 阶段一体检中发现）：世坤101原始公式里
大量直接对 open/high/low/close/vwap 这类绝对价格水平做 `ops.rank()`（横截面排名）。这在
美股语境下问题不大（个股价格经拆股调整后量级相对接近），但加密市场里不同 symbol 的绝对
价格能差出十几个数量级（BTC 几万美元 vs 山寨币零点几美分），直接排绝对价格排的是"谁的
单价更贵"，跟这根K线真实的多空信息无关——`rank_price()` 就是为了收口这一类问题而加的，
见下方它自己的 docstring。
"""

from __future__ import annotations

from typing import Union

import pandas as pd

from .. import ops

Scalar = Union[int, float]


def _valid_mask(cond: pd.DataFrame, nan_sources: tuple[pd.DataFrame, ...]) -> pd.DataFrame | None:
    if not nan_sources:
        return None
    valid = nan_sources[0].notna()
    for source in nan_sources[1:]:
        valid = valid & source.notna()
    return valid


def ternary(
    cond: pd.DataFrame,
    if_true: Union[pd.DataFrame, Scalar],
    if_false: Union[pd.DataFrame, Scalar],
    *nan_sources: pd.DataFrame,
) -> pd.DataFrame:
    """`cond ? if_true : if_false`，`if_true`/`if_false` 可以是 DataFrame 或标量。

    `nan_sources` 是喂进 `cond` 比较表达式的原始 DataFrame（比如 `cond = a < b` 就传
    `a, b`）——`cond` 本身的比较结果不会带 NaN（pandas 的比较运算把 NaN 参与的比较判成
    False），必须显式用原始输入的缺失情况重新盖一遍，见模块 docstring。
    """
    if not isinstance(if_true, pd.DataFrame):
        if_true = pd.DataFrame(if_true, index=cond.index, columns=cond.columns)
    result = if_true.where(cond, if_false)
    valid = _valid_mask(cond, nan_sources)
    return result if valid is None else result.where(valid)


def bool_to_signal(cond: pd.DataFrame, *nan_sources: pd.DataFrame) -> pd.DataFrame:
    """把布尔条件转成 `{0.0, 1.0}` 的浮点信号，`nan_sources` 缺失的地方结果也是 NaN。

    用于公式直接把一个布尔比较的结果（乘上 -1、或者拿去 rank）当作分数的场景，跟
    `ternary` 是同一个 NaN 处理原则，只是没有 if_true/if_false 两个分支。
    """
    result = cond.astype(float)
    valid = _valid_mask(cond, nan_sources)
    return result if valid is None else result.where(valid)


def rank_price(price: pd.DataFrame, periods: int = 1) -> pd.DataFrame:
    """`ops.rank(price)` / `ops.rank(ops.delta(price, periods))` 在世坤因子里的安全替代。

    直接对 open/high/low/close/vwap 这类绝对价格水平做横截面排名，在加密市场会有两种
    表现形式的同一个病根：
    1. **同一根 K 线内部比较**（比如 `rank(open)+rank(low) - rank(high)-rank(close)`）：
       一个 symbol 的开高低收绝对数值彼此接近，只要这个 symbol 是价格分布里的孤立极端值
       （比如 BTC 断层领先所有山寨币），这四个值会被压缩成几乎相同的排名，日内多空信息
       完全读不出来；反过来挤在价格密集区的山寨币，随便一点波动就让排名剧烈跳动，读出来
       的是"邻居多不多"而不是真实价格行为。
    2. **同一个字段跨时间比较**（比如 `ts_cov(rank(close), rank(volume), 5)`）：像 BTC
       这种长期稳坐价格排名头部的 symbol，`rank(close)` 这条时间序列在任意短窗口里几乎
       是一条平线，跟成交量排名的协方差/相关性趋近于 0；而价格密集区的山寨币排名本身就
       更"活跃"，数值更大——同样是密度伪影，不是真实的价量关系强度。

    两种表现形式的根子相同：绝对价格水平不能跨 symbol 直接比较。这里统一换成对
    `price.pct_change(periods)`（相对 `periods` 根之前同一字段的百分比涨跌幅）排名——
    消除了绝对价格量级差异，同时保留了"这个价格字段相对表现"的排序信息。只对本身恒正
    的价格水平（原始字段、或正权重价格加权组合）调用；`a - b` 这类可能跨零的价格差值
    不适用（百分比变化在过零点附近没有意义甚至发散），那类需要单独设计分母，不在这个
    函数的适用范围内。

    只在 `sherpa.alpha.worldquant` 家族内部使用——`BarPanel`/`sherpa.alpha.ops` 的公共
    契约不变，`panel.close`/`panel.open` 等原始字段依旧原样暴露给其它 alpha 家族。
    """
    return ops.rank(price.pct_change(periods=periods))


def rank_price_diff(a: pd.DataFrame, b: pd.DataFrame, reference: pd.DataFrame) -> pd.DataFrame:
    """`ops.rank(a - b)` 的安全替代，用于两个不同原始价格字段的差值。

    跟 `rank_price()` 解决的是同一类问题（绝对价格量级不能跨 symbol 直接比较），但差值
    本身可能穿越 0（比如 `close - vwap` 在均值回归附近会变号），不能像单一价格字段那样直接
    取 `pct_change`——百分比变化在过零点附近没有意义甚至发散。这里改成显式传入一个恒正的
    `reference`（通常是 `delay(close, 1)` 这类锚点，或者 `a`/`b` 中更自然的那一个），返回
    `ops.rank((a - b) / reference)`。
    """
    return ops.rank((a - b) / reference)


def rank_price_distance_from_low(price: pd.DataFrame, window: int) -> pd.DataFrame:
    """`ops.rank(price - ops.ts_min(price, window))` 的安全替代：距自身滚动低点的绝对距离。

    原始写法是绝对美元距离，同样的价格量级问题（见 `rank_price` docstring），换成距滚动
    低点的百分比距离：`ops.rank((price - low) / low)`。
    """
    low = ops.ts_min(price, window)
    return ops.rank((price - low) / low)
