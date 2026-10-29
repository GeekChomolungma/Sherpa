"""威科夫结构：区间假突破（弹簧 / 上冲回落）+ 量价配合。素材：`materials/wyckoff_spring_yekoi.md`（YEKOI 读盘视频）。

视频的做法（ETH 等 1～3 个币，主观画区间）：价格跌破横盘区间下沿、放量下跌，随后缩量不跌、再**放量收回区间**——弹簧，右侧做多；
镜像的上冲回落（UT）是派发结构里的看空信号。泛化到截面：每个币用自己过去一段的高低点当"区间"，每 4 小时给每个币打分，
做多头部、做空尾部（关卡3 的 Top-K 多空）。

**区间**：第 t 根往前、**不含**最近 `probe_bars` 根的 `range_bars` 根里的最高 / 最低价（`range_high` / `range_low`，
宽度 `width`）。最近 `probe_bars` 根是"试探段"：看它有没有刺穿区间、现在收在哪。

分项（全部是原始值，各自在范围内做截面百分位排名后加权；权重 0 = 不用、负 = 反过来用，探索时拆开看）：

- `false_break`（弹簧 − 上冲回落）：试探段最低价刺穿区间下沿的深度（按 `width` 归一，封顶 `pierce_cap`），**当前收盘已回到
  下沿之上**才算弹簧；上冲回落是镜像（刺穿上沿、收盘回到上沿之下）。弹簧为正、上冲回落为负，都没有为 0；
- `break_hold`（突破 / 跌破后收不回来）：收盘在区间上沿之上的距离为正，在下沿之下为负（按 `width` 归一，封顶 `pierce_cap`）。
  视频里的 SOW（放量跌破、不收回）是看空；但截面上它也可能是反转（超跌），方向交给探索；
- `effort`（量价：吸筹 vs 派发）：最近 `effort_bars` 根里上涨 K 线的成交额 − 下跌 K 线的成交额，占总成交额的比例，−1 ~ 1。
  "上涨放量、下跌缩量"为正；
- `reclaim_volume`（放量收回）：最近 `reclaim_bars` 根的平均成交额 / 试探段里更早那几根的平均成交额（取对数）。视频里
  "最后一根放量 K 回到区间内"；只对弹簧 / 上冲回落有意义，所以乘上 `false_break` 的符号（弹簧放量收回 → 更看多，上冲回落
  放量跌回 → 更看空），没有假突破的币为 0；
- `trend`（均线组）：EMA(`ema_fast`) / EMA(`ema_slow`) − 1，快线在慢线之上为正（多头排列）。

做空一侧的派发分项（越大越看空，配 `s_*` 权重用；也能配 `w_*`）：

- `spring` / `upthrust`：`false_break` 拆开的两半（都 >= 0），上冲回落（UT / UTAD）单独当看空信号；
- `supply`（上方抛压）：最近 `supply_bars` 根按成交额加权的上影线占比——冲高被放量打回来；
- `lpsy`（最后供应点）：均线空头排列时，最近 `rally_bars` 根的反弹涨幅 / 同期放量倍数（相对 `effort_bars` 均量）——
  缩量反弹越明显越大；多头排列或没反弹为 0；
- `extension`（买方高潮）：收盘相对慢均线 EMA(`ema_slow`) 的偏离，涨过头越大。

`score = Σ w · rank_in_scope(分项)`，范围外 NaN。

**两条腿分开选**（任一 `s_*` 不为 0 时启用）：多头打分在范围内转成百分位（0～1]；空头分 `Σ s · rank_in_scope(分项)` 排在
范围内前 `short_quantile` 的币，打分改成 −(空头分百分位)，排到所有币的最底下。关卡3 Top-K 做多的仍是多头打分最高的，
做空的是派发特征最强的，而不是"多头分最低"的那一批。具体实例在文件末尾，探索记录见
`research/alpha_research/tradecraft/experiments/FINDINGS_wyckoff.md`。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel

from ...base import register_alpha
from ...liquidity import restrict
from . import indicators
from .base import TradecraftAlpha

COMPONENTS = ("false_break", "break_hold", "effort", "result", "reclaim_volume", "trend",
              "spring", "upthrust", "supply", "lpsy", "extension")


class WyckoffBase(TradecraftAlpha):
    """参数化的威科夫区间 / 量价规则（不注册）。实例 = 子类，只改类属性。"""

    # ---- 区间与试探段 ----
    range_bars: int = 120          # 区间：20 天（视频里的局部结构 20～60 天）
    probe_bars: int = 18           # 试探段：最近 3 天有没有刺穿区间、现在收在哪
    pierce_cap: float = 0.5        # 刺穿深度 / 区间外距离按区间宽度归一后的上限（太深的不是假突破，是趋势）
    # ---- 量价 ----
    effort_bars: int = 42          # 上涨 / 下跌 K 线成交额对比：最近 7 天
    reclaim_bars: int = 3          # 放量收回：最近 3 根 vs 试探段里更早的部分
    # ---- 均线组 ----
    ema_fast: int = 120            # 20 天
    ema_slow: int = 300            # 50 天
    # ---- 权重 ----
    w_false_break: float = 1.0
    w_break_hold: float = 0.0
    w_effort: float = 0.0
    w_result: float = 0.0
    w_reclaim_volume: float = 0.0
    w_trend: float = 0.0
    w_spring: float = 0.0
    w_upthrust: float = 0.0
    w_supply: float = 0.0
    w_lpsy: float = 0.0
    w_extension: float = 0.0
    # ---- 做空一侧（派发）：分项窗口 + 空头分权重（越大越看空）+ 压到底部的比例 ----
    supply_bars: int = 18          # 上方抛压：最近 3 天
    rally_bars: int = 6            # LPSY：最近 1 天的反弹
    s_false_break: float = 0.0
    s_break_hold: float = 0.0
    s_effort: float = 0.0
    s_result: float = 0.0
    s_reclaim_volume: float = 0.0
    s_trend: float = 0.0
    s_spring: float = 0.0
    s_upthrust: float = 0.0
    s_supply: float = 0.0
    s_lpsy: float = 0.0
    s_extension: float = 0.0
    short_quantile: float = 0.2

    @classmethod
    def _used(cls) -> set[str]:
        return {name for name in COMPONENTS if getattr(cls, f"w_{name}") != 0 or getattr(cls, f"s_{name}") != 0}

    @classmethod
    def required_lookback(cls) -> int:
        used = cls._used()
        need = [cls.range_bars + cls.probe_bars, cls.effort_bars + 1, cls.supply_bars]
        if used & {"trend", "lpsy", "extension"}:
            need.append(cls.ema_slow)
        return max(need) + 1

    def __init_subclass__(cls, **kwargs) -> None:
        cls.lookback_bars = cls.required_lookback()
        super().__init_subclass__(**kwargs)

    def weights(self) -> dict[str, float]:
        return {name: float(getattr(self, f"w_{name}")) for name in COMPONENTS}

    def short_weights(self) -> dict[str, float]:
        return {name: float(getattr(self, f"s_{name}")) for name in COMPONENTS}

    def components(self, panel: BarPanel) -> dict[str, pd.DataFrame]:
        """各分项的原始值（不排名）。只算多头或空头权重不为 0 的项。"""
        need = self._used()
        close, high, low = panel.close, panel.high, panel.low
        range_high = high.rolling(self.range_bars).max().shift(self.probe_bars)
        range_low = low.rolling(self.range_bars).min().shift(self.probe_bars)
        width = (range_high - range_low).where(lambda w: w > 0)
        out: dict[str, pd.DataFrame] = {}

        if need & {"false_break", "reclaim_volume", "spring", "upthrust"}:
            pierce_dn = ((range_low - low.rolling(self.probe_bars).min()) / width).clip(lower=0.0, upper=self.pierce_cap)
            pierce_up = ((high.rolling(self.probe_bars).max() - range_high) / width).clip(lower=0.0, upper=self.pierce_cap)
            spring = pierce_dn.where(close > range_low, 0.0).where(width.notna())
            upthrust = pierce_up.where(close < range_high, 0.0).where(width.notna())
            false_break = spring - upthrust
            out["false_break"] = false_break
            out["spring"] = spring
            out["upthrust"] = upthrust
            if "reclaim_volume" in need:
                qv = panel.quote_volume
                recent = qv.rolling(self.reclaim_bars).mean()
                earlier = qv.shift(self.reclaim_bars).rolling(self.probe_bars - self.reclaim_bars).mean()
                ratio = indicators.log_or_nan(recent) - indicators.log_or_nan(earlier)
                out["reclaim_volume"] = np.sign(false_break) * ratio.clip(lower=0.0)
        if "break_hold" in need:
            above = ((close - range_high) / width).clip(lower=0.0, upper=self.pierce_cap)
            below = ((range_low - close) / width).clip(lower=0.0, upper=self.pierce_cap)
            out["break_hold"] = above - below
        if "effort" in need:
            qv = panel.quote_volume
            direction = np.sign(close.diff())
            signed = (qv * direction).rolling(self.effort_bars).sum()
            out["effort"] = signed / qv.rolling(self.effort_bars).sum().where(lambda s: s > 0)
        if "result" in need:
            out["result"] = indicators.returns(panel, self.effort_bars)
        if need & {"trend", "lpsy", "extension"}:
            fast = close.ewm(span=self.ema_fast, min_periods=self.ema_fast).mean()
            slow = close.ewm(span=self.ema_slow, min_periods=self.ema_slow).mean()
            out["trend"] = fast / slow - 1.0
            out["extension"] = close / slow - 1.0
        if "supply" in need:
            qv = panel.quote_volume
            shadow = indicators.upper_shadow_ratio(panel).fillna(0.0)
            out["supply"] = (qv * shadow).rolling(self.supply_bars).sum() / qv.rolling(self.supply_bars).sum().where(lambda s: s > 0)
        if "lpsy" in need:
            rally = indicators.returns(panel, self.rally_bars).clip(lower=0.0)
            surge = indicators.volume_surge(panel, self.rally_bars, self.effort_bars)
            out["lpsy"] = (rally / surge).where(out["trend"] < 0, 0.0).where(out["trend"].notna() & surge.notna())
        return out

    def _composite(self, parts: dict[str, pd.DataFrame], weights: dict[str, float], scope: pd.DataFrame) -> pd.DataFrame:
        terms = [(w, parts[name]) for name, w in weights.items() if w != 0]
        return sum((w * self.rank_in_scope(raw, scope) for w, raw in terms), start=scope.astype("float64") * 0.0)

    def score(self, panel: BarPanel) -> pd.DataFrame:
        scope = self.scope(panel)
        parts = self.components(panel)
        if not any(self.weights().values()):
            raise ValueError(f"{type(self).__name__}：所有分项权重都是 0")
        score = restrict(self._composite(parts, self.weights(), scope), scope)
        if not any(self.short_weights().values()):
            return score
        # 两条腿分开选：多头分转成 (0, 1] 的百分位；空头分排在前 short_quantile 的币压到底部（−空头分百分位 < 0）
        long_pct = score.rank(axis=1, pct=True)
        short_pct = restrict(self._composite(parts, self.short_weights(), scope), scope).rank(axis=1, pct=True)
        flagged = (short_pct > 1.0 - self.short_quantile) & long_pct.notna()
        return restrict(long_pct.mask(flagged, -short_pct), scope)


# ---------------------------------------------------------------------------------------------
# 实例（2026-10-29 探索三批、29 个参数组合，research/alpha_research/tradecraft/experiments/FINDINGS_wyckoff.md）。
# 结论先说：弹簧（假突破）本身在截面上几乎没有排序能力；视频的量价方向（上涨放量、均线多头排列看多）是"中位数效应"——
# RankIC 为负（中位数的币跑输），但高分组平均收益更高、右尾更肥，Top-K 多空扣费后为正。反方向 RankIC 为正，但零成本就亏。
# 两个都进研究线，持有期 6 根（1 天，作者是波段思维；也是 ML 的主口径，能直接跟 V4 比）。
# ---------------------------------------------------------------------------------------------

@register_alpha
class TcWyckoffVideoV1(WyckoffBase):
    """按视频原意：弹簧（试探 1 天、区间 20 天）+ 放量上涨（20 天上涨 K 成交额占比）+ 均线多头排列（EMA 20 天 / 50 天）。

    探索第三批 `video`：RankIC 1 根选 / 验 −0.018 / −0.011、6 根 −0.028 / −0.009（中位数的币跑输）；但关卡3 网格多空
    零成本 0.56 / 0.81、吃单 0.15 / 0.45，两段都为正的组合 59%。研究线要设 `direction: as_is`，不然关卡3 会按选择段 IC
    的符号把它反过来做。
    """

    name = "tc_wyckoff_video_v1"
    horizon_bars = 6
    probe_bars = 6
    w_effort = 1.0
    effort_bars = 120
    w_trend = 1.0


@register_alpha
class TcWyckoffAbsorbV1(WyckoffBase):
    """RankIC 方向：跌出区间收不回来的分高、冲出区间的分低，上涨 K 成交额占比低的分高（20 天）——视频量价方向的反面。

    探索第三批 `absorb`：RankIC 1 根选 / 验 0.022 / 0.018、6 根 0.040 / 0.023，两段稳定；但 Top-K 多空零成本就亏
    （−0.46 / −1.01）：做空的"放量上涨、冲出区间"的币右尾极肥。作为对照留着。
    """

    name = "tc_wyckoff_absorb_v1"
    horizon_bars = 6
    w_false_break = 0.0
    w_break_hold = -1.0
    w_effort = -1.0
    effort_bars = 120


@register_alpha
class TcWyckoffLsV1(TcWyckoffVideoV1):
    """视频多头腿 + 派发空头腿（两条腿分开选）：做多仍按视频原意（弹簧 + 放量上涨 + 多头排列），做空换成
    LPSY（均线空头排列时最近 3 天缩量反弹）+ 空头排列，空头分前 20% 的币压到底部。

    探索第四～六批：派发结构里上方抛压、买方高潮也是"中位数效应"（最像派发的 10% 右尾肥，做空被轧），只有 LPSY 两段
    RankIC 为正、尾超额为负。`w6_short_slow` 的 `v_lpsy18_bear`：吃单网格中位数选 / 验 0.43 / 0.58（视频原版 0.15 / 0.45），
    两段都为正 74%，换手 0.053 / 根；最低 10% 的 6 根超额 −12.4 / −10.2 bps。整体 RankIC 仍由多头打分主导（6 根 −0.012 / 0.006）。
    """

    name = "tc_wyckoff_ls_v1"
    s_lpsy = 1.0
    s_trend = -1.0
    rally_bars = 18
    short_quantile = 0.2
