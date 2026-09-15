"""分类三·动量与趋势反转类（25 个，`101_alpha_factors_classified.md` §三）。

核心假说：价格短期过度反应导致均值回归，或中期惯性形成动量趋势。多个公式用"三元表达式"
描述状态机（涨跌持续/突破/衰减），一律用 `_common.ternary`/`bool_to_signal` 处理 NaN 传播
（设计文档 §6.5 的教训：pandas 比较运算不会自动把 NaN 输入传播成 NaN 输出）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel

from ... import ops
from ...base import WorldQuantAlpha, register_alpha
from .._common import bool_to_signal, ternary


@register_alpha
class Alpha004(WorldQuantAlpha):
    """Alpha#4：低价在横截面上持续偏低的 symbol 做反向。

    (-1 * Ts_Rank(rank(low), 9))
    """

    name = "alpha004"
    min_lookback = 9

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_rank(ops.rank(panel.low), 9)


@register_alpha
class Alpha007(WorldQuantAlpha):
    """Alpha#7：放量期用 7 日价格动量的时序反转，否则给固定 -1。

    ((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) *
     sign(delta(close, 7))) : (-1 * 1))
    """

    name = "alpha007"
    min_lookback = 67

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv20 = ops.adv(panel.volume, 20)
        cond = adv20 < panel.volume
        d7 = ops.delta(panel.close, 7)
        true_branch = (-1 * ops.ts_rank(d7.abs(), 60)) * ops.sign(d7)
        return ternary(cond, true_branch, -1.0, adv20, panel.volume)


@register_alpha
class Alpha008(WorldQuantAlpha):
    """Alpha#8：开盘价与收益率乘积的 10 期差分反转。

    (-1 * rank(((sum(open, 5) * sum(returns, 5)) - delay((sum(open, 5) *
     sum(returns, 5)), 10))))
    """

    name = "alpha008"
    min_lookback = 16

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        product = ops.ts_sum(panel.open, 5) * ops.ts_sum(returns, 5)
        return -1 * ops.rank(product - ops.delay(product, 10))


@register_alpha
class Alpha009(WorldQuantAlpha):
    """Alpha#9：连续同向变动时顺势延续，否则把当根变动反过来。

    ((0 < ts_min(delta(close,1),5)) ? delta(close,1) :
     ((ts_max(delta(close,1),5) < 0) ? delta(close,1) : (-1 * delta(close,1))))

    两个"顺势"分支（连续 5 根都在涨 / 连续 5 根都在跌）取值相同（都是 delta(close,1)），
    所以等价写成 "trending 时取 d，否则取 -d"。
    """

    name = "alpha009"
    min_lookback = 6

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        d = ops.delta(panel.close, 1)
        ts_min, ts_max = ops.ts_min(d, 5), ops.ts_max(d, 5)
        trending = (ts_min > 0) | (ts_max < 0)
        result = d.where(trending, -1 * d)
        # pandas 里 (NaN > 0) 直接算 False 而不是 NaN，5 根滚动窗口不满时 trending 会被
        # 悄悄判成 False，从而在 warmup 阶段冒出一个"看似正常"实则没有意义的数值——
        # 必须显式用 ts_min 的缺失情况把这部分重新盖成 NaN（呼应数据层"不悄悄补数据"的原则）。
        return result.where(ts_min.notna())


@register_alpha
class Alpha010(WorldQuantAlpha):
    """Alpha#10：跟 Alpha#9 同结构，窗口 4，外面再截面排名。

    rank(((0 < ts_min(delta(close, 1), 4)) ? delta(close, 1) :
     ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))))
    """

    name = "alpha010"
    min_lookback = 5

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        d = ops.delta(panel.close, 1)
        ts_min, ts_max = ops.ts_min(d, 4), ops.ts_max(d, 4)
        trending = (ts_min > 0) | (ts_max < 0)
        result = d.where(trending, -1 * d).where(ts_min.notna())
        return ops.rank(result)


@register_alpha
class Alpha019(WorldQuantAlpha):
    """Alpha#19：短期 7 日差分反转的方向，受 250 日长动量强度加权。

    ((-1 * sign(((close - delay(close, 7)) + delta(close, 7)))) *
     (1 + rank((1 + sum(returns, 250)))))
    """

    name = "alpha019"
    min_lookback = 251

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        d7 = ops.delta(panel.close, 7)
        inner = (panel.close - ops.delay(panel.close, 7)) + d7
        part1 = -1 * ops.sign(inner)
        part2 = 1 + ops.rank(1 + ops.ts_sum(returns, 250))
        return part1 * part2


@register_alpha
class Alpha020(WorldQuantAlpha):
    """Alpha#20：昨日高开低三点跳空缺口的复合反转。

    (((-1 * rank((open - delay(high, 1)))) * rank((open - delay(close, 1)))) *
     rank((open - delay(low, 1))))
    """

    name = "alpha020"
    min_lookback = 2

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        part1 = -1 * ops.rank(panel.open - ops.delay(panel.high, 1))
        part2 = ops.rank(panel.open - ops.delay(panel.close, 1))
        part3 = ops.rank(panel.open - ops.delay(panel.low, 1))
        return part1 * part2 * part3


@register_alpha
class Alpha021(WorldQuantAlpha):
    """Alpha#21：布林带式通道突破 + 量能过滤的三段状态机。

    ((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) :
     (((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 :
      (((1 < (volume / adv20)) || ((volume / adv20) == 1)) ? 1 : (-1 * 1))))
    """

    name = "alpha021"
    min_lookback = 20

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv20 = ops.adv(panel.volume, 20)
        ma8 = ops.ts_sum(panel.close, 8) / 8
        sd8 = ops.stddev(panel.close, 8)
        ma2 = ops.ts_sum(panel.close, 2) / 2
        vol_ratio = panel.volume / adv20

        cond1 = (ma8 + sd8) < ma2
        cond2 = ma2 < (ma8 - sd8)
        cond3 = vol_ratio >= 1.0  # 等价于 (1 < ratio) || (ratio == 1)

        innermost = ternary(cond3, 1.0, -1.0, vol_ratio)
        middle = ternary(cond2, 1.0, innermost, ma2, ma8, sd8)
        return ternary(cond1, -1.0, middle, ma8, sd8, ma2)


@register_alpha
class Alpha023(WorldQuantAlpha):
    """Alpha#23：突破 20 日高价均线时用高点差分反转压制，否则不产出信号。

    (((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)
    """

    name = "alpha023"
    min_lookback = 20

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        ma20 = ops.ts_sum(panel.high, 20) / 20
        cond = ma20 < panel.high
        true_branch = -1 * ops.delta(panel.high, 2)
        return ternary(cond, true_branch, 0.0, ma20, panel.high)


@register_alpha
class Alpha024(WorldQuantAlpha):
    """Alpha#24：百日趋势平缓期触底反弹，否则用短期 3 日差分反转。

    ((((delta((sum(close, 100) / 100), 100) / delay(close, 100)) < 0.05) ||
      (... == 0.05)) ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3)))
    """

    name = "alpha024"
    min_lookback = 200

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        ma100 = ops.ts_sum(panel.close, 100) / 100
        ratio = ops.delta(ma100, 100) / ops.delay(panel.close, 100)
        cond = ratio <= 0.05  # 合并 "< 0.05" 与 "== 0.05" 两支
        true_branch = -1 * (panel.close - ops.ts_min(panel.close, 100))
        false_branch = -1 * ops.delta(panel.close, 3)
        return ternary(cond, true_branch, false_branch, ratio)


@register_alpha
class Alpha031(WorldQuantAlpha):
    """Alpha#31：平滑衰减差分排名、短期反转与流动性相关符号的三项复合。

    ((rank(rank(rank(decay_linear((-1 * rank(rank(delta(close, 10)))), 10)))) +
     rank((-1 * delta(close, 3)))) + sign(scale(correlation(adv20, low, 12))))
    """

    name = "alpha031"
    min_lookback = 31

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv20 = ops.adv(panel.volume, 20)
        inner = ops.decay_linear(-1 * ops.rank(ops.rank(ops.delta(panel.close, 10))), 10)
        part1 = ops.rank(ops.rank(ops.rank(inner)))
        part2 = ops.rank(-1 * ops.delta(panel.close, 3))
        part3 = ops.sign(ops.scale(ops.ts_corr(adv20, panel.low, 12)))
        return part1 + part2 + part3


@register_alpha
class Alpha032(WorldQuantAlpha):
    """Alpha#32：7 日均线回归项与 VWAP-滞后收盘长期相关项的加权和。

    (scale(((sum(close, 7) / 7) - close)) + (20 * scale(correlation(vwap,
     delay(close, 5), 230))))
    """

    name = "alpha032"
    min_lookback = 235

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        part1 = ops.scale(ops.ts_sum(panel.close, 7) / 7 - panel.close)
        part2 = 20 * ops.scale(ops.ts_corr(vwap, ops.delay(panel.close, 5), 230))
        return part1 + part2


@register_alpha
class Alpha033(WorldQuantAlpha):
    """Alpha#33：日内收盘/开盘比率的强反转（`^1` 是恒等幂，等价于直接用比率本身）。

    rank((-1 * ((1 - (open / close)) ^ 1)))
    """

    name = "alpha033"
    min_lookback = 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return ops.rank(-1 * (1 - (panel.open / panel.close)))


@register_alpha
class Alpha034(WorldQuantAlpha):
    """Alpha#34：短期波动率压缩程度与单日差分排名的复合反转。

    rank(((1 - rank((stddev(returns, 2) / stddev(returns, 5)))) +
     (1 - rank(delta(close, 1)))))
    """

    name = "alpha034"
    min_lookback = 6

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        ratio = ops.stddev(returns, 2) / ops.stddev(returns, 5)
        part1 = 1 - ops.rank(ratio)
        part2 = 1 - ops.rank(ops.delta(panel.close, 1))
        return ops.rank(part1 + part2)


@register_alpha
class Alpha037(WorldQuantAlpha):
    """Alpha#37：滞后一期的日内差价与 200 日收盘价长期相关，加上当日差价排名。

    (rank(correlation(delay((open - close), 1), close, 200)) + rank((open - close)))
    """

    name = "alpha037"
    min_lookback = 201

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        open_close = panel.open - panel.close
        part1 = ops.rank(ops.ts_corr(ops.delay(open_close, 1), panel.close, 200))
        part2 = ops.rank(open_close)
        return part1 + part2


@register_alpha
class Alpha038(WorldQuantAlpha):
    """Alpha#38：创 10 日新高位置与日内强势（收盘/开盘比）的综合反转。

    ((-1 * rank(Ts_Rank(close, 10))) * rank((close / open)))
    """

    name = "alpha038"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.rank(ops.ts_rank(panel.close, 10)) * ops.rank(panel.close / panel.open)


@register_alpha
class Alpha046(WorldQuantAlpha):
    """Alpha#46：二阶价格加速度的三段式状态机——加速上涨反转、加速下跌顺势、平稳期跟随昨日变化。

    ((0.25 < slope) ? (-1 * 1) : ((slope < 0) ? 1 : ((-1 * 1) * (close - delay(close, 1)))))
    其中 slope = ((delay(close,20)-delay(close,10))/10) - ((delay(close,10)-close)/10)
    """

    name = "alpha046"
    min_lookback = 21

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        slope = self._slope(panel)
        cond1 = slope > 0.25
        cond2 = slope < 0
        false_branch = -1 * (panel.close - ops.delay(panel.close, 1))
        middle = ternary(cond2, 1.0, false_branch, slope)
        return ternary(cond1, -1.0, middle, slope)

    @staticmethod
    def _slope(panel: BarPanel) -> pd.DataFrame:
        return ((ops.delay(panel.close, 20) - ops.delay(panel.close, 10)) / 10) - (
            (ops.delay(panel.close, 10) - panel.close) / 10
        )


@register_alpha
class Alpha049(WorldQuantAlpha):
    """Alpha#49：跟 Alpha#46 同一个 slope，急剧减速（< -0.1）时反转，否则跟随昨日变化。

    (slope < -0.1) ? 1 : ((-1 * 1) * (close - delay(close, 1)))
    """

    name = "alpha049"
    min_lookback = 21

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        slope = Alpha046._slope(panel)
        cond = slope < -0.1
        false_branch = -1 * (panel.close - ops.delay(panel.close, 1))
        return ternary(cond, 1.0, false_branch, slope)


@register_alpha
class Alpha051(WorldQuantAlpha):
    """Alpha#51：跟 Alpha#49 同结构，阈值改成 -0.05（更容易触发反转）。

    (slope < -0.05) ? 1 : ((-1 * 1) * (close - delay(close, 1)))
    """

    name = "alpha051"
    min_lookback = 21

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        slope = Alpha046._slope(panel)
        cond = slope < -0.05
        false_branch = -1 * (panel.close - ops.delay(panel.close, 1))
        return ternary(cond, 1.0, false_branch, slope)


@register_alpha
class Alpha052(WorldQuantAlpha):
    """Alpha#52：5 日支撑位下移幅度，乘以长短期收益率差异排名与近期成交量时序秩。

    ((((-1 * ts_min(low, 5)) + delay(ts_min(low, 5), 5)) * rank(((sum(returns, 240) -
     sum(returns, 20)) / 220))) * ts_rank(volume, 5))
    """

    name = "alpha052"
    min_lookback = 241

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        ts_min5 = ops.ts_min(panel.low, 5)
        part1 = (-1 * ts_min5) + ops.delay(ts_min5, 5)
        part2 = ops.rank((ops.ts_sum(returns, 240) - ops.ts_sum(returns, 20)) / 220)
        part3 = ops.ts_rank(panel.volume, 5)
        return part1 * part2 * part3


@register_alpha
class Alpha086(WorldQuantAlpha):
    """Alpha#86：流动性相关性时序秩 vs 日内均价偏离的截面比较，取反。

    ((Ts_Rank(correlation(close, sum(adv20, 14.7444), 6.00049), 20.4195) <
     rank(((open + close) - (vwap + open)))) * -1)
    """

    name = "alpha086"
    min_lookback = 57

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        vwap = ops.vwap(panel.quote_volume, panel.volume)
        adv20 = ops.adv(panel.volume, 20)
        left = ops.ts_rank(ops.ts_corr(panel.close, ops.ts_sum(adv20, 14), 6), 20)
        right = ops.rank((panel.open + panel.close) - (vwap + panel.open))
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha088(WorldQuantAlpha):
    """Alpha#88：四价秩差分衰减排名与流动性相关时序秩衰减的逐元素极小值。

    min(rank(decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))),
     8.06882)), Ts_Rank(decay_linear(correlation(Ts_Rank(close, 8.44728),
     Ts_Rank(adv60, 20.6966), 8.01266), 6.65053), 2.61957))
    """

    name = "alpha088"
    min_lookback = 92

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv60 = ops.adv(panel.volume, 60)
        left_inner = (ops.rank(panel.open) + ops.rank(panel.low)) - (
            ops.rank(panel.high) + ops.rank(panel.close)
        )
        left = ops.rank(ops.decay_linear(left_inner, 8))
        corr = ops.ts_corr(ops.ts_rank(panel.close, 8), ops.ts_rank(adv60, 20), 8)
        right = ops.ts_rank(ops.decay_linear(corr, 6), 2)
        return np.minimum(left, right)


@register_alpha
class Alpha095(WorldQuantAlpha):
    """Alpha#95：开盘触底程度 vs 均价流动性相关排名 5 次方的时序秩比较。

    (rank((open - ts_min(open, 12.4105))) < Ts_Rank((rank(correlation(sum(((high +
     low) / 2), 19.1351), sum(adv40, 19.1351), 12.8742)) ^ 5), 11.7584))
    """

    name = "alpha095"
    min_lookback = 79

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv40 = ops.adv(panel.volume, 40)
        left = ops.rank(panel.open - ops.ts_min(panel.open, 12))
        mid = (
            ops.rank(
                ops.ts_corr(ops.ts_sum((panel.high + panel.low) / 2, 19), ops.ts_sum(adv40, 19), 12)
            )
            ** 5
        )
        right = ops.ts_rank(mid, 11)
        return bool_to_signal(left < right, left, right)


@register_alpha
class Alpha099(WorldQuantAlpha):
    """Alpha#99：中轴流动性相关 vs 最低价-成交量相关的截面比较，取反。

    ((rank(correlation(sum(((high + low) / 2), 19.8975), sum(adv60, 19.8975), 8.8136)) <
     rank(correlation(low, volume, 6.28259))) * -1)
    """

    name = "alpha099"
    min_lookback = 85

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        adv60 = ops.adv(panel.volume, 60)
        left = ops.rank(
            ops.ts_corr(ops.ts_sum((panel.high + panel.low) / 2, 19), ops.ts_sum(adv60, 19), 8)
        )
        right = ops.rank(ops.ts_corr(panel.low, panel.volume, 6))
        return -1 * bool_to_signal(left < right, left, right)


@register_alpha
class Alpha101(WorldQuantAlpha):
    """Alpha#101：当根K线实体涨跌幅相对振幅的占比——经典"收盘强弱"形态因子。

    ((close - open) / ((high - low) + .001))
    """

    name = "alpha101"
    min_lookback = 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return (panel.close - panel.open) / ((panel.high - panel.low) + 0.001)
