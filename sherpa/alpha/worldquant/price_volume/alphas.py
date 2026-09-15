"""分类二·量价关系与流动性交叉类（28 个，`101_alpha_factors_classified.md` §二）。

核心假说：价格由资金量驱动，通过量价相关性/协方差/成交金额加权捕捉主力吸筹、量价背离与
流动性溢价。公式里的非整数窗口一律按论文约定 `int(floor(d))` 处理（写代码时直接用取整后
的整数常量，不在运行时重复计算）。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ... import ops
from ...base import WorldQuantAlpha, register_alpha
from .._common import bool_to_signal


@register_alpha
class Alpha002(WorldQuantAlpha):
    """Alpha#2：成交量对数加速度与日内收益率截面排名负相关。

    (-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))
    """

    name = "alpha002"
    min_lookback = 8

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        part1 = ops.rank(ops.delta(ops.log(panel.volume), 2))
        part2 = ops.rank((panel.close - panel.open) / panel.open)
        return -1 * ops.ts_corr(part1, part2, 6)


@register_alpha
class Alpha003(WorldQuantAlpha):
    """Alpha#3：开盘价与成交量的横截面负相关。

    (-1 * correlation(rank(open), rank(volume), 10))
    """

    name = "alpha003"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_corr(ops.rank(panel.open), ops.rank(panel.volume), 10)


@register_alpha
class Alpha006(WorldQuantAlpha):
    """Alpha#6：开盘价与成交量的时序负相关（逐 symbol，不做横截面排名）。

    (-1 * correlation(open, volume, 10))
    """

    name = "alpha006"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_corr(panel.open, panel.volume, 10)


@register_alpha
class Alpha011(WorldQuantAlpha):
    """Alpha#11：VWAP 与收盘价的滚动极值离差之和，乘以成交量差分的排名。

    ((rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) *
     rank(delta(volume, 3)))
    """

    name = "alpha011"
    min_lookback = 4

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        diff = vwap - panel.close
        return (ops.rank(ops.ts_max(diff, 3)) + ops.rank(ops.ts_min(diff, 3))) * ops.rank(
            ops.delta(panel.volume, 3)
        )


@register_alpha
class Alpha012(WorldQuantAlpha):
    """Alpha#12：用成交量的变化方向作为价格反转的触发器。

    (sign(delta(volume, 1)) * (-1 * delta(close, 1)))
    """

    name = "alpha012"
    min_lookback = 2

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return ops.sign(ops.delta(panel.volume, 1)) * (-1 * ops.delta(panel.close, 1))


@register_alpha
class Alpha013(WorldQuantAlpha):
    """Alpha#13：收盘价与成交量排名协方差反转。

    (-1 * rank(covariance(rank(close), rank(volume), 5)))
    """

    name = "alpha013"
    min_lookback = 5

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.rank(ops.ts_cov(ops.rank(panel.close), ops.rank(panel.volume), 5))


@register_alpha
class Alpha014(WorldQuantAlpha):
    """Alpha#14：收益率加速度排名与开盘量价相关性的交叉。

    ((-1 * rank(delta(returns, 3))) * correlation(open, volume, 10))
    """

    name = "alpha014"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        part1 = -1 * ops.rank(ops.delta(returns, 3))
        part2 = ops.ts_corr(panel.open, panel.volume, 10)
        return part1 * part2


@register_alpha
class Alpha015(WorldQuantAlpha):
    """Alpha#15：高点-成交量排名相关性的累加反转。

    (-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))
    """

    name = "alpha015"
    min_lookback = 5

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        corr = ops.ts_corr(ops.rank(panel.high), ops.rank(panel.volume), 3)
        return -1 * ops.ts_sum(ops.rank(corr), 3)


@register_alpha
class Alpha016(WorldQuantAlpha):
    """Alpha#16：最高价与成交量排名协方差反转。

    (-1 * rank(covariance(rank(high), rank(volume), 5)))
    """

    name = "alpha016"
    min_lookback = 5

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.rank(ops.ts_cov(ops.rank(panel.high), ops.rank(panel.volume), 5))


@register_alpha
class Alpha017(WorldQuantAlpha):
    """Alpha#17：价格二阶差分与异常成交量冲击的三因子交叉。

    (((-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1))) *
     rank(ts_rank((volume / adv20), 5)))
    """

    name = "alpha017"
    min_lookback = 24

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv20 = ops.adv(panel.volume, 20)
        part1 = -1 * ops.rank(ops.ts_rank(panel.close, 10))
        part2 = ops.rank(ops.delta(ops.delta(panel.close, 1), 1))
        part3 = ops.rank(ops.ts_rank(panel.volume / adv20, 5))
        return part1 * part2 * part3


@register_alpha
class Alpha022(WorldQuantAlpha):
    """Alpha#22：量价相关性动量变化，用波动率排名加权反转。

    (-1 * (delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))))
    """

    name = "alpha022"
    min_lookback = 20

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        corr = ops.ts_corr(panel.high, panel.volume, 5)
        return -1 * (ops.delta(corr, 5) * ops.rank(ops.stddev(panel.close, 20)))


@register_alpha
class Alpha025(WorldQuantAlpha):
    """Alpha#25：跌幅、流动性规模、VWAP 与上影线的综合打分。

    rank(((((-1 * returns) * adv20) * vwap) * (high - close)))
    """

    name = "alpha025"
    min_lookback = 20

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        adv20 = ops.adv(panel.volume, 20)
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        return ops.rank(((-1 * returns) * adv20 * vwap) * (panel.high - panel.close))


@register_alpha
class Alpha027(WorldQuantAlpha):
    """Alpha#27：VWAP-成交量秩相关短期均值，超过阈值时反转多空方向。

    ((0.5 < rank((sum(correlation(rank(volume), rank(vwap), 6), 2) / 2.0))) ?
     (-1 * 1) : 1)
    """

    name = "alpha027"
    min_lookback = 7

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        corr = ops.ts_corr(ops.rank(panel.volume), ops.rank(vwap), 6)
        avg2 = ops.ts_sum(corr, 2) / 2.0
        scored = ops.rank(avg2)
        cond = scored > 0.5
        return bool_to_signal(cond, scored) * -2.0 + 1.0


@register_alpha
class Alpha030(WorldQuantAlpha):
    """Alpha#30：三日连续涨跌方向的持续性排名，用短/长期成交量比值加权反转。

    (((1.0 - rank(((sign((close - delay(close, 1))) + sign((delay(close, 1) -
     delay(close, 2)))) + sign((delay(close, 2) - delay(close, 3)))))) *
     sum(volume, 5)) / sum(volume, 20))
    """

    name = "alpha030"
    min_lookback = 20

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        s1 = ops.sign(panel.close - ops.delay(panel.close, 1))
        s2 = ops.sign(ops.delay(panel.close, 1) - ops.delay(panel.close, 2))
        s3 = ops.sign(ops.delay(panel.close, 2) - ops.delay(panel.close, 3))
        inner = ops.rank(s1 + s2 + s3)
        return ((1.0 - inner) * ops.ts_sum(panel.volume, 5)) / ops.ts_sum(panel.volume, 20)


@register_alpha
class Alpha035(WorldQuantAlpha):
    """Alpha#35：放量 + 窄幅震荡 + 低收益的"主力吸筹"模式。

    ((Ts_Rank(volume, 32) * (1 - Ts_Rank(((close + high) - low), 16))) *
     (1 - Ts_Rank(returns, 32)))
    """

    name = "alpha035"
    min_lookback = 33

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        part1 = ops.ts_rank(panel.volume, 32)
        part2 = 1 - ops.ts_rank((panel.close + panel.high) - panel.low, 16)
        part3 = 1 - ops.ts_rank(returns, 32)
        return part1 * part2 * part3


@register_alpha
class Alpha039(WorldQuantAlpha):
    """Alpha#39：缩量假突破反转，用长周期动量增强。

    ((-1 * rank((delta(close, 7) * (1 - rank(decay_linear((volume / adv20), 9)))))) *
     (1 + rank(sum(returns, 250))))
    """

    name = "alpha039"
    min_lookback = 251

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        adv20 = ops.adv(panel.volume, 20)
        decay = ops.decay_linear(panel.volume / adv20, 9)
        part1 = -1 * ops.rank(ops.delta(panel.close, 7) * (1 - ops.rank(decay)))
        part2 = 1 + ops.rank(ops.ts_sum(returns, 250))
        return part1 * part2


@register_alpha
class Alpha040(WorldQuantAlpha):
    """Alpha#40：高点波动率排名与量价相关性的乘积。

    ((-1 * rank(stddev(high, 10))) * correlation(high, volume, 10))
    """

    name = "alpha040"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.rank(ops.stddev(panel.high, 10)) * ops.ts_corr(panel.high, panel.volume, 10)


@register_alpha
class Alpha043(WorldQuantAlpha):
    """Alpha#43：异常成交量比的时序秩持续性，乘以下跌动量的时序秩。

    (ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))
    """

    name = "alpha043"
    min_lookback = 39

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv20 = ops.adv(panel.volume, 20)
        part1 = ops.ts_rank(panel.volume / adv20, 20)
        part2 = ops.ts_rank(-1 * ops.delta(panel.close, 7), 8)
        return part1 * part2


@register_alpha
class Alpha044(WorldQuantAlpha):
    """Alpha#44：最高价与成交量截面排名的负相关。

    (-1 * correlation(high, rank(volume), 5))
    """

    name = "alpha044"
    min_lookback = 5

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_corr(panel.high, ops.rank(panel.volume), 5)


@register_alpha
class Alpha045(WorldQuantAlpha):
    """Alpha#45：滞后均线的排名、短期量价相关与均线时序相关排名的三重乘积反转。

    (-1 * ((rank((sum(delay(close, 5), 20) / 20)) * correlation(close, volume, 2)) *
     rank(correlation(sum(close, 5), sum(close, 20), 2))))
    """

    name = "alpha045"
    min_lookback = 25

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        delayed = ops.delay(panel.close, 5)
        part1 = ops.rank(ops.ts_sum(delayed, 20) / 20)
        part2 = ops.ts_corr(panel.close, panel.volume, 2)
        part3 = ops.rank(ops.ts_corr(ops.ts_sum(panel.close, 5), ops.ts_sum(panel.close, 20), 2))
        return -1 * (part1 * part2 * part3)


@register_alpha
class Alpha050(WorldQuantAlpha):
    """Alpha#50：VWAP-成交量秩相关性的滚动最大值反转。

    (-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5))
    """

    name = "alpha050"
    min_lookback = 9

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        corr = ops.ts_corr(ops.rank(panel.volume), ops.rank(vwap), 5)
        return -1 * ops.ts_max(ops.rank(corr), 5)


@register_alpha
class Alpha056(WorldQuantAlpha):
    """Alpha#56：收益率累加比值与市值-收益冲击反转（依赖市值 `cap`，`BarPanel` 不支持）。

    (0 - (1 * (rank((sum(returns, 10) / sum(sum(returns, 2), 3))) *
     rank((returns * cap)))))

    跟 indneutralize 缺行业数据同一个原则（设计文档 §6.3 决策2）：`BarPanel` 没有市值字段，
    不拿代理维度（比如用成交额近似市值）硬凑，宁可不实现。
    """

    name = "alpha056"

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        raise NotImplementedError("alpha056 依赖市值(cap)数据，当前 BarPanel 不支持（同 §6.3 决策2 的原则）")


@register_alpha
class Alpha061(WorldQuantAlpha):
    """Alpha#61：VWAP 触底程度 vs 长期流动性相关性的截面比较。

    (rank((vwap - ts_min(vwap, 16.1219))) < rank(correlation(vwap, adv180, 17.9282)))
    """

    name = "alpha061"
    min_lookback = 180

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv180 = ops.adv(panel.volume, 180)
        left = ops.rank(vwap - ops.ts_min(vwap, 16))
        right = ops.rank(ops.ts_corr(vwap, adv180, 17))
        return bool_to_signal(left < right, left, right)


@register_alpha
class Alpha062(WorldQuantAlpha):
    """Alpha#62：VWAP-流动性相关排名 vs 开盘中枢偏离布尔对抗，取反。

    ((rank(correlation(vwap, sum(adv20, 22.4101), 9.91009)) < rank(((rank(open) +
     rank(open)) < (rank(((high + low) / 2)) + rank(high))))) * -1)
    """

    name = "alpha062"
    min_lookback = 50

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv20 = ops.adv(panel.volume, 20)
        left = ops.rank(ops.ts_corr(vwap, ops.ts_sum(adv20, 22), 9))
        inner_cond = (ops.rank(panel.open) + ops.rank(panel.open)) < (
            ops.rank((panel.high + panel.low) / 2) + ops.rank(panel.high)
        )
        inner_signal = bool_to_signal(inner_cond, panel.open, panel.high, panel.low)
        right = ops.rank(inner_signal)
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha064(WorldQuantAlpha):
    """Alpha#64：加权低点流动性相关 vs 加权均价速度的截面比较，取反。

    ((rank(correlation(sum(((open * 0.178404) + (low * (1 - 0.178404))), 12.7054),
     sum(adv120, 12.7054), 16.6208)) < rank(delta(((((high + low) / 2) * 0.178404) +
     (vwap * (1 - 0.178404))), 3.69741))) * -1)
    """

    name = "alpha064"
    min_lookback = 146

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv120 = ops.adv(panel.volume, 120)
        weighted_ol = panel.open * 0.178404 + panel.low * (1 - 0.178404)
        left = ops.rank(ops.ts_corr(ops.ts_sum(weighted_ol, 12), ops.ts_sum(adv120, 12), 16))
        weighted_hlv = ((panel.high + panel.low) / 2) * 0.178404 + vwap * (1 - 0.178404)
        right = ops.rank(ops.delta(weighted_hlv, 3))
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha074(WorldQuantAlpha):
    """Alpha#74：收盘流动性相关 vs 均价成交量秩相关的截面比较，取反。

    ((rank(correlation(close, sum(adv30, 37.4843), 15.1365)) < rank(correlation(
     rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11.4791))) * -1)
    """

    name = "alpha074"
    min_lookback = 81

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv30 = ops.adv(panel.volume, 30)
        left = ops.rank(ops.ts_corr(panel.close, ops.ts_sum(adv30, 37), 15))
        weighted = panel.high * 0.0261661 + vwap * (1 - 0.0261661)
        right = ops.rank(ops.ts_corr(ops.rank(weighted), ops.rank(panel.volume), 11))
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha075(WorldQuantAlpha):
    """Alpha#75：VWAP 量能相关 vs 低点流动性秩相关的截面比较。

    (rank(correlation(vwap, volume, 4.24304)) < rank(correlation(rank(low),
     rank(adv50), 12.4413)))
    """

    name = "alpha075"
    min_lookback = 61

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv50 = ops.adv(panel.volume, 50)
        left = ops.rank(ops.ts_corr(vwap, panel.volume, 4))
        right = ops.rank(ops.ts_corr(ops.rank(panel.low), ops.rank(adv50), 12))
        return bool_to_signal(left < right, left, right)


@register_alpha
class Alpha078(WorldQuantAlpha):
    """Alpha#78：加权低点流动性相关排名与 VWAP 量能秩相关排名的幂运算。

    (rank(correlation(sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 19.7428),
     sum(adv40, 19.7428), 6.83313)) ^ rank(correlation(rank(vwap), rank(volume), 5.77492)))

    公式里的 `^` 是幂运算（论文约定），不是按位异或。
    """

    name = "alpha078"
    min_lookback = 63

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv40 = ops.adv(panel.volume, 40)
        weighted = panel.low * 0.352233 + vwap * (1 - 0.352233)
        left = ops.rank(ops.ts_corr(ops.ts_sum(weighted, 19), ops.ts_sum(adv40, 19), 6))
        right = ops.rank(ops.ts_corr(ops.rank(vwap), ops.rank(panel.volume), 5))
        return left**right
