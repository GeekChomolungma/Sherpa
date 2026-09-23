"""分类五·复合极值与非线性时序衰减类（12 个，`101_alpha_factors_classified.md` §五；该节
标题写"14个"，但表格实际列了 12 条——三个分类小节都有类似的标题计数与实际行数不一致的
情况，代码以表格实际内容为准，5 个分类总数加总仍然是 101）。

核心假说：近期信息权重高于远期（线性衰减），拐点（极值发生日）具有前瞻指示力，符号幂
变换放大极端多空标的的得分差异。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel

from ... import ops
from ...base import WorldQuantAlpha, register_alpha
from .._common import bool_to_signal, rank_price, rank_price_diff, rank_price_distance_from_low


@register_alpha
class Alpha001(WorldQuantAlpha):
    """Alpha#1：下跌时用波动率、上涨时用收盘价，找窗口内极值出现的位置。

    (rank(Ts_ArgMax(SignedPower(((returns<0) ? stddev(returns,20) : close), 2), 5)) - 0.5)
    """

    name = "alpha001"
    min_lookback = 25  # 20（stddev窗口）+ 5（ts_argmax窗口）

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        base = ops.stddev(returns, 20).where(returns < 0, panel.close)
        powered = ops.signed_power(base, 2)
        return ops.rank(ops.ts_argmax(powered, 5)) - 0.5


@register_alpha
class Alpha026(WorldQuantAlpha):
    """Alpha#26：成交量与最高价时序秩相关性的滚动最大值反转。

    (-1 * ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))
    """

    name = "alpha026"
    min_lookback = 11

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        corr = ops.ts_corr(ops.ts_rank(panel.volume, 5), ops.ts_rank(panel.high, 5), 5)
        return -1 * ops.ts_max(corr, 3)


@register_alpha
class Alpha029(WorldQuantAlpha):
    """Alpha#29：深度嵌套的多重截面秩与对数缩放复合，叠加滞后收益时序秩。

    (min(product(rank(rank(scale(log(sum(ts_min(rank(rank((-1 * rank(delta((close - 1),
     5))))), 2), 1))))), 1), 5) + ts_rank(delay((-1 * returns), 6), 5))

    `delta((close-1),5)` 代数上等于 `delta(close,5)`（常数在差分里抵消）；`sum(x,1)` 和
    `product(x,1)` 窗口为 1，等价于恒等变换，代码里直接省略这两步。
    """

    name = "alpha029"
    min_lookback = 12

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        # rank(delta(close,5)) 排的是绝对美元涨跌，同一个病根见 _common.rank_price docstring，
        # 换成百分比涨跌幅。
        step1 = -1 * ops.rank(panel.close.pct_change(periods=5))
        step2 = ops.rank(ops.rank(step1))
        step3 = ops.ts_min(step2, 2)
        step4 = np.log(step3)
        step5 = ops.scale(step4)
        step6 = ops.rank(ops.rank(step5))
        part1 = np.minimum(step6, 5.0)
        part2 = ops.ts_rank(ops.delay(-1 * returns, 6), 5)
        return part1 + part2


@register_alpha
class Alpha036(WorldQuantAlpha):
    """Alpha#36：经典多因子经验回归加权线性集成（五项排名分数按固定系数相加）。

    (2.21 * rank(correlation((close - open), delay(volume, 1), 15))) +
     (0.7 * rank((open - close))) +
     (0.73 * rank(Ts_Rank(delay((-1 * returns), 6), 5))) +
     rank(abs(correlation(vwap, adv20, 6))) +
     (0.6 * rank((((sum(close, 200) / 200) - open) * (close - open))))
    """

    name = "alpha036"
    min_lookback = 200

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv20 = ops.adv(panel.volume, 20)
        open_close = panel.close - panel.open

        part1 = 2.21 * ops.rank(ops.ts_corr(open_close, ops.delay(panel.volume, 1), 15))
        # part2：open-close 是绝对美元差值，可能跨 0，以 close 为锚点换成百分比
        # （见 _common.rank_price_diff docstring）。系数 0.7 是给 rank() 输出（值域固定在
        # (0,1]）配权重，不受价格量级影响，不用跟着换算。
        part2 = 0.7 * rank_price_diff(panel.open, panel.close, panel.close)
        part3 = 0.73 * ops.rank(ops.ts_rank(ops.delay(-1 * returns, 6), 5))
        part4 = ops.rank(ops.ts_corr(vwap, adv20, 6).abs())
        # part5：((sum(close,200)/200)-open) 和 open_close 都是绝对美元差值，相乘后量纲
        # 是 [价格]^2，同一个跨 symbol 价格问题；分别以 open 为锚点换成百分比再相乘，
        # 乘积才是无量纲的。
        ma200_deviation = ((ops.ts_sum(panel.close, 200) / 200) - panel.open) / panel.open
        pct_open_close = open_close / panel.open
        part5 = 0.6 * ops.rank(ma200_deviation * pct_open_close)
        return part1 + part2 + part3 + part4 + part5


@register_alpha
class Alpha071(WorldQuantAlpha):
    """Alpha#71：收盘-流动性相关衰减时序秩与均价偏离平方衰减时序秩的逐元素极大值。

    max(Ts_Rank(decay_linear(correlation(Ts_Rank(close, 3.43976), Ts_Rank(adv180,
     12.0647), 18.0175), 4.20501), 15.6948), Ts_Rank(decay_linear((rank(((low + open) -
     (vwap + vwap))) ^ 2), 16.4662), 4.4388))
    """

    name = "alpha071"
    min_lookback = 226

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv180 = ops.adv(panel.volume, 180)
        corr = ops.ts_corr(ops.ts_rank(panel.close, 3), ops.ts_rank(adv180, 12), 18)
        left = ops.ts_rank(ops.decay_linear(corr, 4), 15)
        squared = ops.rank((panel.low + panel.open) - (vwap + vwap)) ** 2
        right = ops.ts_rank(ops.decay_linear(squared, 16), 4)
        return np.maximum(left, right)


@register_alpha
class Alpha072(WorldQuantAlpha):
    """Alpha#72：中轴-流动性相关衰减排名 除以 VWAP-成交量时序秩相关衰减排名。

    (rank(decay_linear(correlation(((high + low) / 2), adv40, 8.93345), 10.1519)) /
     rank(decay_linear(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188),
     6.86671), 2.95011)))
    """

    name = "alpha072"
    min_lookback = 57

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv40 = ops.adv(panel.volume, 40)
        corr1 = ops.ts_corr((panel.high + panel.low) / 2, adv40, 8)
        left = ops.rank(ops.decay_linear(corr1, 10))
        corr2 = ops.ts_corr(ops.ts_rank(vwap, 3), ops.ts_rank(panel.volume, 18), 6)
        right = ops.rank(ops.decay_linear(corr2, 2))
        return left / right  # rank() 值域 (0,1]，分母不会是 0，不需要额外防护


@register_alpha
class Alpha081(WorldQuantAlpha):
    """Alpha#81：流动性相关 4 次方连乘对数的截面排名 vs VWAP-成交量相关排名，取反。

    ((rank(Log(product(rank((rank(correlation(vwap, sum(adv10, 49.6054), 8.47743)) ^ 4)),
     14.9655))) < rank(correlation(rank(vwap), rank(volume), 5.07914))) * -1)
    """

    name = "alpha081"
    min_lookback = 78

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv10 = ops.adv(panel.volume, 10)
        corr_pow4 = ops.rank(ops.ts_corr(vwap, ops.ts_sum(adv10, 49), 8)) ** 4
        product = ops.ts_product(ops.rank(corr_pow4), 14)
        left = ops.rank(np.log(product))
        right = ops.rank(ops.ts_corr(rank_price(vwap), ops.rank(panel.volume), 5))
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha084(WorldQuantAlpha):
    """Alpha#84：VWAP 新高离差的时序秩，做符号幂变换，指数是收盘价 4 日差分（逐元素变化）。

    SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))
    """

    name = "alpha084"
    min_lookback = 34

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        # base 是 ts_rank 的输出，逐 symbol 自比较，天然跟绝对价格量级无关，不用改。
        # exponent 是绝对美元 4 日差分——这不是"跨 symbol 排名"意义上的病根，而是更隐蔽的
        # 第三种表现形式：signed_power(base, exponent) 里 exponent 直接决定了这个幂函数
        # 的形状，BTC 的 exponent 可能是几百，山寨币可能是 0.0001，同一个 base 在不同
        # symbol 上被抬到天差地别的次方，曲线形状完全不可比。换成百分比涨跌幅，exponent
        # 变成一个小的、跨 symbol 量级可比的分数。
        base = ops.ts_rank(vwap - ops.ts_max(vwap, 15), 20)
        exponent = panel.close.pct_change(periods=4)
        return ops.signed_power(base, exponent)


@register_alpha
class Alpha085(WorldQuantAlpha):
    """Alpha#85：高收加权流动性相关排名 与 中轴-成交量时序秩相关排名 的幂运算。

    (rank(correlation(((high * 0.876703) + (close * (1 - 0.876703))), adv30, 9.61331)) ^
     rank(correlation(Ts_Rank(((high + low) / 2), 3.70596), Ts_Rank(volume, 10.1595),
     7.11408)))
    """

    name = "alpha085"
    min_lookback = 39

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv30 = ops.adv(panel.volume, 30)
        weighted = panel.high * 0.876703 + panel.close * (1 - 0.876703)
        left = ops.rank(ops.ts_corr(weighted, adv30, 9))
        corr2 = ops.ts_corr(ops.ts_rank((panel.high + panel.low) / 2, 3), ops.ts_rank(panel.volume, 10), 7)
        right = ops.rank(corr2)
        return left**right


@register_alpha
class Alpha094(WorldQuantAlpha):
    """Alpha#94：VWAP 低点离差排名 与 流动性相关时序秩 的幂运算，取反。

    ((rank((vwap - ts_min(vwap, 11.5783))) ^ Ts_Rank(correlation(Ts_Rank(vwap, 19.6462),
     Ts_Rank(adv60, 4.02992), 18.0926), 2.70756)) * -1)
    """

    name = "alpha094"
    min_lookback = 82

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv60 = ops.adv(panel.volume, 60)
        left = rank_price_distance_from_low(vwap, window=11)
        corr = ops.ts_corr(ops.ts_rank(vwap, 19), ops.ts_rank(adv60, 4), 18)
        right = ops.ts_rank(corr, 2)
        return -1 * (left**right)


@register_alpha
class Alpha096(WorldQuantAlpha):
    """Alpha#96：VWAP-成交量相关衰减时序秩 与 极值发生日的多重时序秩衰减 的逐元素极大值，取反。

    (max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume), 3.83878), 4.16783),
     8.38151), Ts_Rank(decay_linear(Ts_ArgMax(correlation(Ts_Rank(close, 7.45404),
     Ts_Rank(adv60, 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1)
    """

    name = "alpha096"
    min_lookback = 101

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv60 = ops.adv(panel.volume, 60)
        corr1 = ops.ts_corr(rank_price(vwap), ops.rank(panel.volume), 3)
        left = ops.ts_rank(ops.decay_linear(corr1, 4), 8)
        corr2 = ops.ts_corr(ops.ts_rank(panel.close, 7), ops.ts_rank(adv60, 4), 3)
        argmax = ops.ts_argmax(corr2, 12)
        right = ops.ts_rank(ops.decay_linear(argmax, 14), 13)
        return -1 * np.maximum(left, right)


@register_alpha
class Alpha098(WorldQuantAlpha):
    """Alpha#98：VWAP 短期流动性相关衰减排名 减去 极小日发生位置的时序秩衰减排名。

    (rank(decay_linear(correlation(vwap, sum(adv5, 26.4719), 4.58418), 7.18088)) -
     rank(decay_linear(Ts_Rank(Ts_ArgMin(correlation(rank(open), rank(adv15), 20.8187),
     8.62571), 6.95668), 8.07206)))
    """

    name = "alpha098"
    min_lookback = 53

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv5 = ops.adv(panel.volume, 5)
        adv15 = ops.adv(panel.volume, 15)
        corr1 = ops.ts_corr(vwap, ops.ts_sum(adv5, 26), 4)
        left = ops.rank(ops.decay_linear(corr1, 7))
        corr2 = ops.ts_corr(rank_price(panel.open), ops.rank(adv15), 20)
        argmin = ops.ts_argmin(corr2, 8)
        ts_ranked = ops.ts_rank(argmin, 6)
        right = ops.rank(ops.decay_linear(ts_ranked, 8))
        return left - right
