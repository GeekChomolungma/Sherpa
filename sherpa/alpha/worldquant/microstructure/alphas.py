"""分类四·高低价差与盘口结构类（18 个，`101_alpha_factors_classified.md` §四）。

核心假说：单日 K 线内部包含买卖压力博弈信息，通过最高价/最低价/收盘价/VWAP 之间的几何
偏离量化多空力量。这一类公式经常出现"高减低""收盘减最低"这类分母，flat bar（`high==low`
或 `close==low`）时会除零——统一加 `_EPS` 保护（`101_alpha_factors_classified.md` §四工程
指引原话："对于涉及分母的公式...增加 eps=1e-7...防止生成无穷大值"，原文列举的 #53/#54/#83
只是举例，不是穷尽，这里对所有同类分母都一致处理）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel

from ... import ops
from ...base import WorldQuantAlpha, register_alpha
from .._common import bool_to_signal, rank_price, rank_price_diff, rank_price_distance_from_low

_EPS = 1e-7


@register_alpha
class Alpha005(WorldQuantAlpha):
    """Alpha#5：开盘价偏离 10 日 VWAP 均线，乘以收盘-VWAP 偏离绝对值排名的负值。

    (rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))
    """

    name = "alpha005"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        avg_vwap = ops.ts_sum(vwap, 10) / 10
        # 两个都是绝对美元差值，可能跨 0，分别以各自的参照价格为锚点换成百分比
        # （见 _common.rank_price_diff docstring）。
        part1 = rank_price_diff(panel.open, avg_vwap, avg_vwap)
        part2 = -1 * rank_price_diff(panel.close, vwap, vwap).abs()
        return part1 * part2


@register_alpha
class Alpha018(WorldQuantAlpha):
    """Alpha#18：日内实体振幅标准差、当日差价与开收相关性的综合反转。

    (-1 * rank(((stddev(abs((close - open)), 5) + (close - open)) +
     correlation(close, open, 10))))
    """

    name = "alpha018"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        # 原始写法把绝对美元量纲的项（stddev(|close-open|,5)、close-open）跟无量纲的相关
        # 系数直接加在一起，量纲上本来就不该相加；换成 (close-open)/open 的百分比版本，
        # 三项才是真正同一量级、可以相加的量（见 _common.rank_price docstring 的同一个
        # 跨 symbol 价格问题）。
        pct_open_close = (panel.close - panel.open) / panel.open
        inner = ops.stddev(pct_open_close.abs(), 5) + pct_open_close + ops.ts_corr(panel.close, panel.open, 10)
        return -1 * ops.rank(inner)


@register_alpha
class Alpha028(WorldQuantAlpha):
    """Alpha#28：流动性-最低价相关加权的中枢价与收盘价差，做截面缩放。

    scale(((correlation(adv20, low, 5) + ((high + low) / 2)) - close))
    """

    name = "alpha028"
    min_lookback = 24

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv20 = ops.adv(panel.volume, 20)
        # ts_corr 项无量纲，((high+low)/2 - close) 是绝对美元差值——同一个跨 symbol 价格
        # 问题（见 _common.rank_price docstring），以 close 为锚点换成百分比。
        midpoint_deviation = ((panel.high + panel.low) / 2 - panel.close) / panel.close
        inner = ops.ts_corr(adv20, panel.low, 5) + midpoint_deviation
        return ops.scale(inner)


@register_alpha
class Alpha041(WorldQuantAlpha):
    """Alpha#41：高低几何均价对 VWAP 的偏离度。

    (((high * low) ^ 0.5) - vwap)
    """

    name = "alpha041"
    min_lookback = 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        # 原始写法没有任何截面/时序比较算子包裹，是纯逐元素计算，但返回值本身仍带着绝对
        # 美元量纲——最终会被下游 rank_ic()/组合构建跨 symbol 比较（见 _common.rank_price
        # docstring 的同一个病根），以 vwap 为锚点换成百分比偏离。
        geometric_mean = (panel.high * panel.low) ** 0.5
        return (geometric_mean - vwap) / vwap


@register_alpha
class Alpha042(WorldQuantAlpha):
    """Alpha#42（Delay-0）：日内 VWAP 均值回归——VWAP 偏离与均值的截面排名比值。

    (rank((vwap - close)) / rank((vwap + close)))
    """

    name = "alpha042"
    min_lookback = 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        # 分子 vwap-close 可能跨 0，以 close 为锚点换成百分比；分母 vwap+close 恒正，但
        # 仍是绝对美元量纲，注意 rank(x/c) 和 rank(x/c + 1) 排名完全一样（常数不改变
        # 相对顺序），所以 rank(vwap/close) 等价于 rank((vwap+close)/close)，写法更简单
        # （见 _common.rank_price/rank_price_diff docstring 的同一个病根）。
        return rank_price_diff(vwap, panel.close, panel.close) / ops.rank(vwap / panel.close)


@register_alpha
class Alpha047(WorldQuantAlpha):
    """Alpha#47：低价股放量、上影线打压程度与 VWAP 5 日动量排名的组合。

    ((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) /
     (sum(high, 5) / 5))) - rank((vwap - delay(vwap, 5))))

    核心项 `rank(1/close)` 想捕捉美股语境下的"低价股效应"（绝对价格低的股票有系统性的
    行为差异，比如更容易被散户炒作）——这不是单位换算能修的问题，是整个经济假设在加密
    市场不成立：币的绝对价格只是发行总量决定的任意数字（一个项目把总量发多 100 倍，
    单价就变成 1/100，不代表任何行为差异），不存在"低价币效应"这回事。跟 alpha046/049/051
    缺原则性阈值依据同理，不硬凑一个"修好"的版本，宁可不实现。
    """

    name = "alpha047"
    min_lookback = 20

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        raise NotImplementedError(
            "alpha047 核心项 rank(1/close) 依赖的'低价股效应'是美股语境下的行为假设，"
            "加密市场里币的绝对单价只是发行量决定的任意数字，这个前提不成立，不臆造替代，宁可不实现"
        )


@register_alpha
class Alpha053(WorldQuantAlpha):
    """Alpha#53（Delay-0）：盘口买卖力量比率（收盘-最低 vs 最高-收盘）的 9 期差分反转。

    (-1 * delta((((close - low) - (high - close)) / (close - low)), 9))
    """

    name = "alpha053"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        denom = (panel.close - panel.low) + _EPS
        inner = ((panel.close - panel.low) - (panel.high - panel.close)) / denom
        return -1 * ops.delta(inner, 9)


@register_alpha
class Alpha054(WorldQuantAlpha):
    """Alpha#54（Delay-0）：高阶非线性开收高低价偏离比率。

    ((-1 * ((low - close) * (open ^ 5))) / ((low - high) * (close ^ 5)))
    """

    name = "alpha054"
    min_lookback = 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        numerator = -1 * ((panel.low - panel.close) * (panel.open**5))
        denom = ((panel.low - panel.high) * (panel.close**5)) + _EPS
        return numerator / denom


@register_alpha
class Alpha055(WorldQuantAlpha):
    """Alpha#55：KDJ/Stochastics 式随机指标（12 日）与成交量截面排名的负相关。

    (-1 * correlation(rank(((close - ts_min(low, 12)) / (ts_max(high, 12) -
     ts_min(low, 12)))), rank(volume), 6))
    """

    name = "alpha055"
    min_lookback = 17

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        ts_min12 = ops.ts_min(panel.low, 12)
        ts_max12 = ops.ts_max(panel.high, 12)
        stochastic = (panel.close - ts_min12) / ((ts_max12 - ts_min12) + _EPS)
        return -1 * ops.ts_corr(ops.rank(stochastic), ops.rank(panel.volume), 6)


@register_alpha
class Alpha057(WorldQuantAlpha):
    """Alpha#57：收盘与 VWAP 的差值，受"最高点发生日排名"的线性衰减抑制。

    (0 - (1 * ((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))))
    """

    name = "alpha057"
    min_lookback = 31

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        decay = ops.decay_linear(ops.rank(ops.ts_argmax(panel.close, 30)), 2)
        # decay 本身是位置索引（ts_argmax）经过 rank/decay_linear，天然无量纲；分子
        # close-vwap 是绝对美元差值，除以一个无量纲分母并不能消除这个量纲问题（见
        # _common.rank_price docstring），以 vwap 为锚点先换成百分比。
        return -1 * ((panel.close - vwap) / vwap) / (decay + _EPS)


@register_alpha
class Alpha060(WorldQuantAlpha):
    """Alpha#60：日内资金流向排名缩放的两倍，减去"最高点发生日排名"缩放，整体取反。

    (0 - (1 * ((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) *
     volume)))) - scale(rank(ts_argmax(close, 10))))))
    """

    name = "alpha060"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        denom = (panel.high - panel.low) + _EPS
        money_flow = (((panel.close - panel.low) - (panel.high - panel.close)) / denom) * panel.volume
        part1 = 2 * ops.scale(ops.rank(money_flow))
        part2 = ops.scale(ops.rank(ops.ts_argmax(panel.close, 10)))
        return -1 * (part1 - part2)


@register_alpha
class Alpha065(WorldQuantAlpha):
    """Alpha#65：加权开盘-VWAP 与流动性相关 vs 开盘触底程度的截面比较，取反。

    ((rank(correlation(((open * 0.00817205) + (vwap * (1 - 0.00817205))),
     sum(adv60, 8.6911), 6.40374)) < rank((open - ts_min(open, 13.635)))) * -1)
    """

    name = "alpha065"
    min_lookback = 73

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv60 = ops.adv(panel.volume, 60)
        weighted = panel.open * 0.00817205 + vwap * (1 - 0.00817205)
        left = ops.rank(ops.ts_corr(weighted, ops.ts_sum(adv60, 8), 6))
        right = rank_price_distance_from_low(panel.open, window=13)
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha066(WorldQuantAlpha):
    """Alpha#66：VWAP 差分衰减排名，加上日内振幅中枢偏离衰减的时序秩，取反。

    ((rank(decay_linear(delta(vwap, 3.51013), 7.23052)) + Ts_Rank(decay_linear(
     ((((low * 0.96633) + (low * (1 - 0.96633))) - vwap) / (open - ((high + low) / 2))),
     11.4157), 6.72611)) * -1)

    公式里 `(low*0.96633)+(low*(1-0.96633))` 是同一个变量 `low` 加权自身，代数上恒等于
    `low`——照抄原始公式的写法保留系数，但计算时直接用 `low`。
    """

    name = "alpha066"
    min_lookback = 26

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        # delta(vwap,3) 是绝对美元变化，外面还要 rank——跟 rank_price 要解决的同一个病根
        # （见 _common.rank_price docstring），这里换成百分比涨跌幅，decay_linear/rank 结构不变。
        part1 = ops.rank(ops.decay_linear(vwap.pct_change(periods=3), 7))
        denom = (panel.open - ((panel.high + panel.low) / 2)) + _EPS
        inner2 = (panel.low - vwap) / denom
        part2 = ops.ts_rank(ops.decay_linear(inner2, 11), 6)
        return -1 * (part1 + part2)


@register_alpha
class Alpha068(WorldQuantAlpha):
    """Alpha#68：高点流动性相关时序秩 vs 加权收盘-低点差分的截面比较，取反。

    ((Ts_Rank(correlation(rank(high), rank(adv15), 8.91644), 13.9333) <
     rank(delta(((close * 0.518371) + (low * (1 - 0.518371))), 1.06157))) * -1)
    """

    name = "alpha068"
    min_lookback = 34

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv15 = ops.adv(panel.volume, 15)
        left = ops.ts_rank(ops.ts_corr(rank_price(panel.high), ops.rank(adv15), 8), 13)
        weighted = panel.close * 0.518371 + panel.low * (1 - 0.518371)
        right = rank_price(weighted)
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha073(WorldQuantAlpha):
    """Alpha#73：VWAP 差分衰减排名与加权开盘-低点跌幅衰减时序秩的逐元素极大值，取反。

    (max(rank(decay_linear(delta(vwap, 4.72775), 2.91864)), Ts_Rank(decay_linear(
     ((delta(((open * 0.147155) + (low * (1 - 0.147155))), 2.03608) / ((open * 0.147155) +
     (low * (1 - 0.147155)))) * -1), 3.33829), 16.7411)) * -1)
    """

    name = "alpha073"
    min_lookback = 19

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        left = ops.rank(ops.decay_linear(vwap.pct_change(periods=4), 2))
        weighted = panel.open * 0.147155 + panel.low * (1 - 0.147155)
        inner2 = (ops.delta(weighted, 2) / (weighted + _EPS)) * -1
        right = ops.ts_rank(ops.decay_linear(inner2, 3), 16)
        return -1 * np.maximum(left, right)


@register_alpha
class Alpha077(WorldQuantAlpha):
    """Alpha#77：中轴偏离 VWAP 的衰减排名与中轴-流动性相关衰减排名的逐元素极小值。

    min(rank(decay_linear(((((high + low) / 2) + high) - (vwap + high)), 20.0451)),
     rank(decay_linear(correlation(((high + low) / 2), adv40, 3.1614), 5.64125)))
    """

    name = "alpha077"
    min_lookback = 46

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv40 = ops.adv(panel.volume, 40)
        # 代数化简：((high+low)/2 + high) - (vwap+high) = (high+low)/2 - vwap，绝对美元
        # 差值可能跨 0，以 vwap 为锚点换成百分比（见 _common.rank_price_diff docstring）。
        midpoint = (panel.high + panel.low) / 2
        left = ops.rank(ops.decay_linear((midpoint - vwap) / vwap, 20))
        corr = ops.ts_corr((panel.high + panel.low) / 2, adv40, 3)
        right = ops.rank(ops.decay_linear(corr, 5))
        return np.minimum(left, right)


@register_alpha
class Alpha083(WorldQuantAlpha):
    """Alpha#83：滞后 2 期的振幅比率排名乘以双重成交量排名，除以当期振幅比率与 VWAP 偏离比。

    (rank(delay(((high - low) / (sum(close, 5) / 5)), 2)) * rank(rank(volume))) /
     (((high - low) / (sum(close, 5) / 5)) / (vwap - close))
    """

    name = "alpha083"
    min_lookback = 7

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        ratio = (panel.high - panel.low) / (ops.ts_sum(panel.close, 5) / 5)
        numerator = ops.rank(ops.delay(ratio, 2)) * ops.rank(ops.rank(panel.volume))
        # (vwap-close) 是绝对美元差值——分母整体本来应该是无量纲比值，混进一个带价格
        # 量纲的项，会让最终结果也带上价格量纲（见 _common.rank_price docstring 的同一个
        # 病根）。以 close 为锚点换成百分比。
        pct_vwap_close = (vwap - panel.close) / panel.close
        denom = (ratio / (pct_vwap_close + _EPS)) + _EPS
        return numerator / denom


@register_alpha
class Alpha092(WorldQuantAlpha):
    """Alpha#92：日内重心低位（布尔信号）衰减时序秩 vs 低点-流动性相关衰减时序秩的逐元素极小值。

    min(Ts_Rank(decay_linear(((((high + low) / 2) + close) < (low + open)), 14.7221),
     18.8683), Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 7.58555),
     6.94024), 6.80584))
    """

    name = "alpha092"
    min_lookback = 46

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv30 = ops.adv(panel.volume, 30)
        cond = (((panel.high + panel.low) / 2) + panel.close) < (panel.low + panel.open)
        signal = bool_to_signal(cond, panel.high, panel.low, panel.close, panel.open)
        left = ops.ts_rank(ops.decay_linear(signal, 14), 18)
        corr = ops.ts_corr(rank_price(panel.low), ops.rank(adv30), 7)
        right = ops.ts_rank(ops.decay_linear(corr, 6), 6)
        return np.minimum(left, right)
