"""放量蓄势：在"短期流动性暴增"的币里挑"放了量但还没涨出去"的，避开"已经冲高、涨幅在缩小"的；横盘震荡的行情不参与。

交易原则（用户的交易经验，2026-10-28）：

1. **候选池**：按短期成交额增量（最近 `surge_short` 根平均成交额 / 最近 `surge_long` 根平均成交额）在截面上排序，只在
   增量排在前 `pool_quantile` 的币里交易——有资金突然关注的币才有行情；
2. **池内打分**（三项各自在池内做截面百分位排名，再加权）：
   - **涨幅变化率**（`indicators.return_acceleration`，最近 `accel_bars` 根平均逐根收益 − 之前 `accel_bars` 根）：
     变化率为负 = 涨幅在缩小、上涨衰竭 → 分低；
   - **已经涨了多少**（最近 `breakout_bars` 根涨幅）：放了量但还没涨出去的分高，已经放量突破的分低；
   - **上影线**（最近 `shadow_bars` 根上影线占振幅的平均比例）：冲高被打回来、上方抛压重 → 分低；
   `score = w_accel·rank(变化率) − w_breakout·rank(涨幅) − w_shadow·rank(上影线)`。权重可以为 0（不用这一项）或负（反过来用），
   探索时用来拆开看每一项各自有没有用；
3. **择时**：大盘（`gate_symbol`，默认 BTC）最近 `gate_bars` 根的趋势效率（`indicators.efficiency_ratio`，净位移 / 走过的路）
   低于它过去 `gate_history` 根的 `gate_quantile` 分位时，认为是横盘 / 来回震荡，**这一期全部币不打分（NaN）**——
   NaN 才是"不参与"：不排名、不开仓；全设成 0 的话所有币并列，排序没有意义，Top-K 还是会在并列里挑币开仓。
   `gate_quantile = 0` 关掉择时。

池外的币、择时关闭的期都是 NaN。具体实例（参数组合）在本文件末尾，探索记录见
`research/alpha_research/tradecraft/experiments/`。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ...base import register_alpha
from ...liquidity import restrict
from . import indicators
from .base import TradecraftAlpha


class LiquiditySurgeBase(TradecraftAlpha):
    """参数化的放量蓄势规则（不注册）。实例 = 子类，只改类属性。"""

    # ---- 1. 候选池 ----
    surge_short: int = 6          # 短期：最近 1 天
    surge_long: int = 42          # 对比基准：最近 7 天
    pool_quantile: float = 0.3    # 只要放量程度排在前 30% 的币
    # ---- 2. 池内打分 ----
    accel_bars: int = 3           # 涨幅变化率：最近 3 根 vs 之前 3 根
    breakout_bars: int = 6        # 已经涨了多少：最近 6 根（1 天）涨幅
    shadow_bars: int = 3          # 上影线：最近 3 根平均
    w_accel: float = 1.0
    w_breakout: float = 1.0
    w_shadow: float = 1.0
    # 两种口径（探索里比过，见 research/alpha_research/tradecraft/experiments/FINDINGS.md）：
    # accel_kind  "signed" = 变化率越大分越高；"flat" = 变化率越接近 0（涨幅平缓）分越高
    # breakout_kind "return" = 最近 breakout_bars 根涨幅；"range" = 收盘价在最近 breakout_bars 根高低区间里的位置（0 底 1 顶）
    accel_kind: str = "signed"
    breakout_kind: str = "return"
    # 已经暴涨的不碰：池内最近 breakout_bars 根涨幅排在前这个比例的币直接 NaN（不参与）。冲高的币右尾极肥（少数会继续暴涨），
    # 打低分去做空它们会被轧（探索第二批诊断，FINDINGS.md）。0 = 不排除
    exclude_top_breakout: float = 0.0
    # ---- 3. 择时（横盘 / 震荡不参与）----
    gate_symbol: str = "BTCUSDT"
    gate_bars: int = 42
    gate_quantile: float = 0.0    # 0 = 不择时
    gate_history: int = 6 * 180   # 分位数用过去多少根 bar 的历史

    @classmethod
    def required_lookback(cls) -> int:
        need = max(cls.surge_long, 2 * cls.accel_bars, cls.breakout_bars, cls.shadow_bars) + 1
        if cls.gate_quantile > 0:
            need = max(need, cls.gate_bars + cls.gate_history)
        return need

    def __init_subclass__(cls, **kwargs) -> None:
        cls.lookback_bars = cls.required_lookback()
        super().__init_subclass__(**kwargs)

    def pool(self, panel: BarPanel, scope: pd.DataFrame) -> pd.DataFrame:
        """候选池：范围内、短期放量程度排在前 `pool_quantile` 的币。"""
        surge = indicators.volume_surge(panel, self.surge_short, self.surge_long)
        return self.rank_in_scope(surge, scope) > 1.0 - self.pool_quantile

    def active(self, panel: BarPanel) -> pd.Series:
        """每一期要不要交易：大盘趋势效率不低于过去的 `gate_quantile` 分位。历史不够长的早期照常交易。"""
        if self.gate_quantile <= 0:
            return pd.Series(True, index=panel.close.index)
        er = indicators.efficiency_ratio(panel.close[self.gate_symbol], self.gate_bars)
        threshold = er.rolling(self.gate_history, min_periods=self.gate_history // 2).quantile(self.gate_quantile)
        return ~(er < threshold)  # er 或阈值是 NaN（历史不够）时照常交易

    def components(self, panel: BarPanel) -> dict[str, pd.DataFrame]:
        """三项原始值（不排名），探索时拆开分析用。"""
        accel = indicators.return_acceleration(panel, self.accel_bars)
        if self.accel_kind == "flat":
            accel = -accel.abs()
        elif self.accel_kind != "signed":
            raise ValueError(f"accel_kind 只能是 signed / flat，收到 {self.accel_kind!r}")
        if self.breakout_kind == "return":
            breakout = indicators.returns(panel, self.breakout_bars)
        elif self.breakout_kind == "range":
            breakout = indicators.range_position(panel, self.breakout_bars)
        else:
            raise ValueError(f"breakout_kind 只能是 return / range，收到 {self.breakout_kind!r}")
        return {
            "accel": accel,
            "breakout": breakout,
            "shadow": indicators.upper_shadow_ratio(panel).rolling(self.shadow_bars).mean(),
        }

    def score(self, panel: BarPanel) -> pd.DataFrame:
        scope = self.scope(panel)
        in_pool = scope & self.pool(panel, scope)
        parts = self.components(panel)
        if self.exclude_top_breakout > 0:
            run_up = restrict(indicators.returns(panel, self.breakout_bars), in_pool).rank(axis=1, pct=True)
            in_pool = in_pool & ~(run_up > 1.0 - self.exclude_top_breakout)

        def rank(x: pd.DataFrame) -> pd.DataFrame:
            return restrict(x, in_pool).rank(axis=1, pct=True)

        # 权重为 0 的项跳过（不然 0 × NaN 还是 NaN，会把这一项缺数据的币也弄成没分）
        terms = [(self.w_accel, "accel"), (-self.w_breakout, "breakout"), (-self.w_shadow, "shadow")]
        score = sum((w * rank(parts[name]) for w, name in terms if w != 0), start=in_pool.astype("float64") * 0.0)
        return score.where(in_pool).where(self.active(panel), axis=0)


# ---------------------------------------------------------------------------------------------
# 实例（2026-10-28 探索四批、35 个参数组合后定下，research/alpha_research/tradecraft/experiments/FINDINGS.md）。
# 结论先说：池内排序能力是真的（6 根 RankIC 跟 V4 同一量级、两段都成立），但 Top-K 等权多空扣费后不赚钱——
# 打最低分的"已经冲高"的币右尾极肥，做空它们被少数继续暴涨的币轧掉；换手也是 V4 的两倍。
# ---------------------------------------------------------------------------------------------

@register_alpha
class TcSurgeCalmV1(LiquiditySurgeBase):
    """按原话的三条：放量前 30% 的币里，涨幅变化率平缓、还没涨出去、上影线短的分高；已经冲高、涨幅在缩小的分低。

    变化率用"平缓"的理解（|最近 3 根平均逐根收益 − 之前 3 根| 越小分越高）：探索第二批里它比"越加速分越高"好得多
    （1 根 RankIC 选 / 验 0.036 / 0.041 vs 0.030 / 0.020）。不择时。
    """

    name = "tc_surge_calm_v1"
    accel_kind = "flat"


@register_alpha
class TcSurgeCalmV2(TcSurgeCalmV1):
    """V1 把窗口拉长：变化率、上影线看 1 天（6 根），涨幅看 2 天（12 根）。

    探索第四批选择段最好的一个（1 根 RankIC 选 / 验 0.042 / 0.042，6 根 0.077 / 0.061）：信号能持续一天左右，
    看太短的窗口噪声大。换手只从 0.31 降到 0.27 / 根，扣费仍然亏。
    """

    name = "tc_surge_calm_v2"
    accel_bars = 6
    shadow_bars = 6
    breakout_bars = 12


@register_alpha
class TcSurgeCalmGatedV1(TcSurgeCalmV1):
    """V1 + 原则 3：BTC 最近 7 天趋势效率低于过去 180 天的 33% 分位（横盘 / 来回震荡）时，整期不打分、不交易。

    探索第三批：关掉 1/3 最震荡的时段后，剩下时段的 RankIC 基本不变（选 / 验 0.034 / 0.041 vs 不择时 0.036 / 0.041）——
    这套排序在震荡期并不比趋势期差，择时没有带来排序上的好处。留着它是为了让原则 3 有一个正式实例可以跟踪。
    注意关卡3 的 04 表会剔除选择段空仓 > 20% 的组合，主动空仓的择时实例在那里可能一个组合都不剩，要看不剔除的数字。
    """

    name = "tc_surge_calm_gated_v1"
    gate_quantile = 0.33


@register_alpha
class TcSurgeCalmV2H2(TcSurgeCalmV2):
    """V2 的打分原样不动，持有期压到 2 根（8 小时）：步骤 0 的 RankIC 按 2 根算，配合研究线的只做多回测（调仓每 2 / 3 根）。

    来自用户的改进（2026-10-28）：① 只买 Top-K、不做空——第一批诊断里亏钱的是空头腿（做空冲高的币被轧）；
    ② 持有时间压到 2～3 根 bar。只做多不是市场中性，看结果时要跟等权基准比（`run_long_only.py`）。
    """

    name = "tc_surge_calm_v2_h2"
    horizon_bars = 2


@register_alpha
class TcSurgeCalmV2H3(TcSurgeCalmV2):
    """同 `TcSurgeCalmV2H2`，持有期 3 根（12 小时）。"""

    name = "tc_surge_calm_v2_h3"
    horizon_bars = 3
