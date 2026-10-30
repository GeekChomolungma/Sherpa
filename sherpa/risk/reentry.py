"""组合熔断后的恢复入场规则：熔断期间每根 bar 问一次"现在可以重新建仓了吗"。

规则只读 `ReentryContext`——这次熔断的影子组合（`shadow_book.ShadowBook`）、截面行情的逐期统计（`MarketTape`）、
不加止损的全程净值——全部是决策时刻已知的数据，所以规则怎么组合都不会偷看未来。

```python
BookStop(vol_mult=1.5, reentry=AllOf((ShadowReboundScaled(0.5), MarketCalm(window=42, ratio=1.0))))
```

新规则：写一个 frozen dataclass，带 `name` 类属性和 `ready(ctx) -> bool`，用 `@register` 注册（`to_dict` / `from_dict`
靠它往返，方案要能写进产出的元数据）。`min_flat_bars` 是 `BookStop` 上的硬下限，不归规则管。

只依赖 numpy，跟 `sherpa.risk` 其余模块同一条包级约定。
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any, ClassVar, Sequence

import numpy as np

from sherpa.risk.shadow_book import ShadowBook


class MarketTape:
    """截面行情的逐期统计，由 `StopController` 每根 bar 追加一次（用决策时刻已知的收盘价推出的那根收益）：

    - `market`：有价格的币等权平均收益（"大盘"）；
    - `dispersion`：截面收益的标准差（币之间分化有多大）。
    """

    def __init__(self) -> None:
        self.market: list[float] = []
        self.dispersion: list[float] = []

    def append(self, realized: np.ndarray, valid: np.ndarray) -> None:
        values = realized[valid]
        self.market.append(float(values.mean()) if values.size else 0.0)
        self.dispersion.append(float(values.std()) if values.size > 1 else 0.0)

    def __len__(self) -> int:
        return len(self.market)

    def vol(self, window: int, end: int | None = None) -> float:
        """截至第 `end` 根（不含，默认最新）最近 `window` 根大盘收益的标准差；数据不够返回 NaN。"""
        return _window_stat(self.market, window, end, np.std)

    def mean_dispersion(self, window: int, end: int | None = None) -> float:
        """截至第 `end` 根（不含）最近 `window` 根截面分化的均值；数据不够返回 NaN。"""
        return _window_stat(self.dispersion, window, end, np.mean)


def _window_stat(series: list[float], window: int, end: int | None, fn) -> float:
    end = len(series) if end is None else end
    if window < 1 or end < window:
        return float("nan")
    return float(fn(series[end - window:end]))


@dataclass(frozen=True)
class ReentryContext:
    """熔断期间某一根 bar 上，恢复入场规则能看到的全部信息。"""

    shadow: ShadowBook                  # 这次熔断的影子组合（`shadow.bars` = 熔断后过了几根）
    market: MarketTape                  # 截面行情统计（全程）
    market_at_trip: int                 # 熔断那一根时 `market` 的长度：`market.vol(w, end=market_at_trip)` = 熔断时的大盘波动
    unstopped_path: Sequence[float]     # 不加止损的全程毛净值（已记账部分），最后一个是当前值
    trip_threshold: float = float("nan")  # 这次熔断时的回撤阈值（动态阈值时就是当时按波动算出来的那个）


# ---- 规则 ----------------------------------------------------------------------------------------
_REGISTRY: dict[str, type] = {}


def register(cls):
    _REGISTRY[cls.name] = cls
    return cls


class ReentryRule:
    name: ClassVar[str]

    def ready(self, ctx: ReentryContext) -> bool:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.name, **{f.name: getattr(self, f.name) for f in fields(self)}}


def reentry_from_dict(raw: dict[str, Any]) -> ReentryRule:
    raw = dict(raw)
    cls = _REGISTRY[raw.pop("rule")]
    return cls.from_dict(raw) if hasattr(cls, "from_dict") else cls(**raw)


@register
@dataclass(frozen=True)
class UnstoppedAboveMean(ReentryRule):
    """（`book10` 的原始口径）不加止损的全程净值站上它最近 `bars` 根的均值。"""

    name: ClassVar[str] = "unstopped_above_mean"
    bars: int = 42

    def ready(self, ctx: ReentryContext) -> bool:
        path = ctx.unstopped_path
        return len(path) >= self.bars and path[-1] > float(np.mean(path[-self.bars:]))


@register
@dataclass(frozen=True)
class ShadowRebound(ReentryRule):
    """影子组合从熔断以来的最低点反弹了至少 `rebound`（比如 0.05 = 5%）：止损之后的下跌已经见底回升。"""

    name: ClassVar[str] = "shadow_rebound"
    rebound: float = 0.05

    def ready(self, ctx: ReentryContext) -> bool:
        return ctx.shadow.rebound >= self.rebound


@register
@dataclass(frozen=True)
class ShadowReboundScaled(ReentryRule):
    """影子组合从最低点反弹至少 `of_threshold` × 这次熔断的阈值：阈值按波动定，反弹的门槛也就跟着波动走，不另设百分比。"""

    name: ClassVar[str] = "shadow_rebound_scaled"
    of_threshold: float = 0.5

    def ready(self, ctx: ReentryContext) -> bool:
        return bool(np.isfinite(ctx.trip_threshold)) and ctx.shadow.rebound >= self.of_threshold * ctx.trip_threshold


@register
@dataclass(frozen=True)
class MaxFlat(ReentryRule):
    """超时兜底：熔断后空仓满 `bars` 根，不管影子怎样都恢复（防止一直等不到信号、长期空仓）。"""

    name: ClassVar[str] = "max_flat"
    bars: int = 42

    def ready(self, ctx: ReentryContext) -> bool:
        return ctx.shadow.bars >= self.bars


@register
@dataclass(frozen=True)
class ShadowRecovered(ReentryRule):
    """影子组合相对开端（熔断那一刻）的涨跌不低于 `level`：0 = 收复熔断以来的全部亏损，负数 = 允许还差一点。"""

    name: ClassVar[str] = "shadow_recovered"
    level: float = 0.0

    def ready(self, ctx: ReentryContext) -> bool:
        return ctx.shadow.change >= self.level


@register
@dataclass(frozen=True)
class MarketCalm(ReentryRule):
    """大盘波动回落：最近 `window` 根大盘收益的波动不超过熔断时（同样窗口）的 `ratio` 倍。熔断时数据不够就不拦。"""

    name: ClassVar[str] = "market_calm"
    window: int = 42
    ratio: float = 1.0

    def ready(self, ctx: ReentryContext) -> bool:
        at_trip = ctx.market.vol(self.window, end=ctx.market_at_trip)
        now = ctx.market.vol(self.window)
        if not np.isfinite(at_trip) or not np.isfinite(now):
            return True
        return now <= self.ratio * at_trip


@dataclass(frozen=True)
class _Combine(ReentryRule):
    rules: tuple[ReentryRule, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"rule": self.name, "rules": [r.to_dict() for r in self.rules]}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]):
        return cls(tuple(reentry_from_dict(r) for r in raw["rules"]))


@register
@dataclass(frozen=True)
class AllOf(_Combine):
    """全部满足才入场。"""

    name: ClassVar[str] = "all_of"

    def ready(self, ctx: ReentryContext) -> bool:
        return all(r.ready(ctx) for r in self.rules)


@register
@dataclass(frozen=True)
class AnyOf(_Combine):
    """任一满足就入场。"""

    name: ClassVar[str] = "any_of"

    def ready(self, ctx: ReentryContext) -> bool:
        return any(r.ready(ctx) for r in self.rules)
