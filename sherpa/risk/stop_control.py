"""止损控制：目标权重路径 → 逐期实际持仓（`held`）之间的一层，打分（alpha）始终不感知仓位和盈亏。

```text
alpha 打分 ─► 排名 ─► 目标权重路径 targets（无状态，`score_backtest.target_path`）
                              │
                              ▼  每根 bar：StopController.step(close, target, holding)
                         实际持仓 held ─► 回测引擎算换手 / 收益（研究线）、生成调仓意图（Runner）
```

对外是一个黑盒，守住三条，内部规则怎么升级都不影响调用方：

1. **只减风险**：输出不超过"不加止损时这一期会持有的仓位"（调仓行 = 目标，非调仓行 = 最近一次目标随价格漂移到现在），
   同号、绝对值不超过它——只会平仓 / 缩小，不开策略之外的仓、不加仓、不反手。选币永远是 alpha 和权重映射的事；
2. **因果**：触发判断只用决策时刻 t 已知的价格（`close`）。漂移后的持仓 `holding` 在 `shift > 1` 时已经用到了
   t 之后的收益（执行时刻的持仓），只当"保持不动"的基础仓位，不参与判断；
3. **规则全空 = 不干预**：输出等于原来的 `held`（调仓行 = 目标，非调仓行 = 漂移后的持仓）。

两类规则，组合熔断优先：

- **组合熔断**（`BookStop`）：每根 bar 都检查（不管是不是调仓行），组合毛净值相对峰值的回撤到阈值就把全部持仓平掉，
  进入熔断。阈值固定（`max_drawdown`）或按不加止损的组合最近 `vol_bars` 根的波动动态算（`vol_mult` × 波动，
  `drawdown_limit()`）。熔断期间打分照常输出、目标照常算，只是不执行。熔断那一刻拍下被平掉的持仓，启动这次熔断的
  **影子组合**（`shadow_book.ShadowBook`），继续记账；每根 bar 用**恢复入场规则**（`reentry.py`，可替换、可组合）
  看影子组合、截面行情等决策时刻已知的信息，判断能否解除熔断。解除当根**直接满仓**：调仓行按目标，非调仓行按最近一次
  目标随价格漂移到现在的仓位（就是不加止损时此刻会持有的仓位），不等下一个调仓行。影子组合结束，峰值重置为解除时的净值
  （否则离旧峰值还差一个阈值，一恢复就再次熔断）；另外记一个从不重置的历史最高净值 `high_water`，只记录、不参与逻辑；
- **单币止损**（`SymbolStop`，简单实现）：持仓相对建仓参考价（开仓那次决策时刻的收盘价）按方向浮亏到 `stop_loss`，
  当根平掉并锁定；直到某个调仓行的目标里不再有它或方向翻转（信号重置过了），才解锁，之后再进入目标算新的进场。
  空出来的仓位留现金，不由下一名递补。

**净值口径**：组合 / 影子净值都是毛净值（不扣成本），用决策时刻已知的收盘价递推：第 i 步收到 `close[t_i]`，
就知道第 `i − shift` 步决策的持仓在它持有期里实现的收益 `held[i−shift] · (close[t_i] / close[t_{i−1}] − 1)`——
跟向量化回测第 `i − shift` 行的毛收益逐项相同（单测核对），只是晚 `shift` 根才看到，这正是现实中能看到的时点。
不扣成本是为了让触发跟成本假设无关：研究线仍然"零成本跑一次、再按成本扣"。

跟 `sherpa.risk` 其余模块同一条包级约定：只依赖 numpy / pandas，不 import 仓库内其他模块；数组按调用方给的同一组
symbol 对齐（形状 `(N,)`），时间戳只用来给事件打标签。
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Hashable, Optional, Sequence

import numpy as np
import pandas as pd

from sherpa.risk.reentry import (AllOf, MarketCalm, MarketTape, ReentryContext, ReentryRule, ShadowReboundScaled,
                                 reentry_from_dict)
from sherpa.risk.shadow_book import ShadowBook, _drift


def drawdown_limit(bar_returns: Sequence[float], *, vol_mult: float, vol_bars: int) -> float:
    """动态熔断阈值 = `vol_mult` × 最近 `vol_bars` 根逐 bar 收益的标准差 × √`vol_bars`（这段时间尺度上的波动）。
    数据不够 `vol_bars` 根返回 NaN；结果截到 (0, 0.99)。"""
    if len(bar_returns) < vol_bars:
        return float("nan")
    sigma = float(np.std(bar_returns[-vol_bars:])) * np.sqrt(vol_bars)
    return float(np.clip(vol_mult * sigma, 1e-6, 0.99))


def _default_reentry() -> ReentryRule:
    return AllOf((ShadowReboundScaled(0.5), MarketCalm(window=42, ratio=1.0)))


@dataclass(frozen=True)
class BookStop:
    """组合熔断：毛净值相对峰值回撤到阈值就全部平仓；按 `reentry` 规则恢复，恢复当根满仓。

    阈值：`vol_mult` 为 None 时固定 `max_drawdown`；否则动态 = `vol_mult` × 不加止损的组合最近 `vol_bars` 根的波动
    （`drawdown_limit()`），数据还不够 `vol_bars` 根时先用 `max_drawdown`。
    """

    max_drawdown: float = 0.10     # 固定阈值；动态阈值数据不够时的兜底
    vol_mult: Optional[float] = None   # 动态阈值：几倍波动（比如 1.5）
    vol_bars: int = 180            # 动态阈值的波动窗口（180 根 4h = 30 天）
    min_flat_bars: int = 0         # 接口：熔断后至少空仓几根才问恢复规则（0 = 不限制）
    reentry: ReentryRule = field(default_factory=_default_reentry)   # 默认：影子反弹半个阈值、且大盘波动不高于熔断时
    shadow_follow_targets: bool = True   # 影子组合从快照出发后跟随目标调仓（核心）；False = 冻结快照只漂移（接口）

    def __post_init__(self) -> None:
        if not 0 < self.max_drawdown < 1:
            raise ValueError(f"max_drawdown 要在 (0, 1) 之间，收到 {self.max_drawdown}")
        if self.vol_mult is not None and (self.vol_mult <= 0 or self.vol_bars < 2):
            raise ValueError(f"vol_mult > 0、vol_bars >= 2，收到 {self.vol_mult} / {self.vol_bars}")
        if self.min_flat_bars < 0:
            raise ValueError(f"min_flat_bars >= 0，收到 {self.min_flat_bars}")

    def to_dict(self) -> dict[str, Any]:
        return {"max_drawdown": self.max_drawdown, "vol_mult": self.vol_mult, "vol_bars": self.vol_bars,
                "min_flat_bars": self.min_flat_bars, "reentry": self.reentry.to_dict(),
                "shadow_follow_targets": self.shadow_follow_targets}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "BookStop":
        raw = dict(raw)
        if "reentry" in raw:
            raw["reentry"] = reentry_from_dict(raw["reentry"])
        return cls(**raw)


@dataclass(frozen=True)
class SymbolStop:
    """单币止损（简单实现）：按方向浮亏到 `stop_loss` 平仓并锁定，信号重置后解锁。"""

    stop_loss: float = 0.05

    def __post_init__(self) -> None:
        if not 0 < self.stop_loss < 1:
            raise ValueError(f"stop_loss 要在 (0, 1) 之间，收到 {self.stop_loss}")


@dataclass(frozen=True)
class StopRules:
    """一套止损方案。两项都是 None = 不干预。"""

    book: Optional[BookStop] = None
    symbol: Optional[SymbolStop] = None

    @property
    def active(self) -> bool:
        return self.book is not None or self.symbol is not None

    def to_dict(self) -> dict[str, Any]:
        return {"book": None if self.book is None else self.book.to_dict(),
                "symbol": None if self.symbol is None else asdict(self.symbol)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StopRules":
        book, symbol = raw.get("book"), raw.get("symbol")
        return cls(book=None if book is None else BookStop.from_dict(book), symbol=None if symbol is None else SymbolStop(**symbol))


class StopController:
    """有状态的止损控制，每根 bar 按时间顺序调用一次 `step()`。一次回测 / 一条实盘链路一个实例，不要复用。

    `shift`：决策到持仓开始赚钱隔几根（同 `run_vectorized_backtest` 的 `shift = 1 + 执行延迟`），用来把已实现的收益
    对到当初做决策的那一步。
    """

    def __init__(self, rules: StopRules, n_symbols: int, *, shift: int = 1):
        if shift < 1:
            raise ValueError(f"shift 至少是 1，收到 {shift}")
        self.rules = rules
        self.shift = shift
        n = n_symbols
        self._close_prev: Optional[np.ndarray] = None
        self._return_prev = np.zeros(n)          # 上一步得知的已实现收益（第 i−1−shift 步决策的持有期）
        # 最近 shift 步的 (实际持仓, 目标或 None)：等收益实现了再拿来记账
        self._pending: deque[tuple[np.ndarray, Optional[np.ndarray]]] = deque()
        self._unstopped = np.zeros(n)            # 已记账的最近一步、不加止损时的持仓
        self.reference = np.zeros(n)             # 不加止损时此刻会持有的仓位：最近一次目标随价格（决策时刻已知）漂移到现在
        self.equity = 1.0                        # 组合毛净值（已实现部分）
        self.peak = 1.0                          # 判断熔断用的峰值，恢复时重置
        self.high_water = 1.0                    # 历史最高净值，从不重置（只记录总回撤，不参与逻辑）
        self.unstopped_equity = 1.0              # 同一条目标路径、不加任何止损的毛净值
        self.unstopped_path: list[float] = []
        self.unstopped_returns: list[float] = []  # 不加止损的逐 bar 毛收益（动态阈值的波动从这里算）
        self.market = MarketTape()
        self.threshold = rules.book.max_drawdown if rules.book else float("nan")   # 当前的熔断阈值
        self.tripped = False
        self.shadow: Optional[ShadowBook] = None  # 这次熔断的影子组合；不在熔断中为 None
        self._market_at_trip = 0
        self._trip_threshold = float("nan")
        self._step = 0
        # 单币止损的状态
        self._entry = np.full(n, np.nan)
        self._direction = np.zeros(n)
        self._locked = np.zeros(n, dtype=bool)
        self._locked_dir = np.zeros(n)
        self.events: list[dict[str, Any]] = []

    # ------------------------------------------------------------------------------------------
    def step(
        self, *, close: np.ndarray, target: Optional[np.ndarray], holding: np.ndarray, label: Hashable = None
    ) -> np.ndarray:
        """决策时刻 t：`close` = t 的收盘价（NaN = 没价格）；`target` = 调仓行的目标权重，非调仓行 None；
        `holding` = 当前（漂移后）的实际持仓。返回这一期实际持有的权重。"""
        close = np.asarray(close, dtype=float)
        holding = np.asarray(holding, dtype=float)
        target = None if target is None else np.asarray(target, dtype=float)
        base = holding if target is None else target
        if not self.rules.active:
            return base.copy()

        realized = self._settle(close)
        self.reference = target.copy() if target is not None else _drift(self.reference, realized)
        if self.shadow is not None:
            self.shadow.settle(realized)
        status = self._check_book(label, holding) if self.rules.book is not None else None
        if self.tripped:
            held = np.zeros_like(base)
            self._reset_symbols()
        else:
            # 恢复当根直接满仓：非调仓行的 holding 是熔断期间的 0，改用不加止损时此刻会持有的仓位
            held = (self.reference if status == "resume" else base).copy()
            if self.rules.symbol is not None:
                held = self._apply_symbol_stops(close, target, held, label)
        if self.shadow is not None and status != "trip":  # 熔断那一步的决策就是快照，建影子时已经放进去了
            self.shadow.push(target)
        self._pending.append((held.copy(), None if target is None else target.copy()))
        self._close_prev = close
        self._step += 1
        return held

    def events_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.events, columns=["time", "event", "symbol", "equity", "drawdown", "threshold",
                                                  "total_drawdown", "unstopped_equity", "shadow_equity",
                                                  "shadow_rebound", "flat_bars", "pnl"])

    # ------------------------------------------------------------------------------------------
    def _settle(self, close: np.ndarray) -> np.ndarray:
        """记账：这一步得知的已实现收益 = 第 step−shift 步决策的持仓在它持有期里的收益。返回这根 bar 的已实现收益。"""
        if self._close_prev is None:
            realized = np.zeros_like(close)
            valid = np.zeros(close.shape, dtype=bool)
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                realized = close / self._close_prev - 1.0
            valid = np.isfinite(realized)
            realized = np.where(valid, realized, 0.0)
        self.market.append(realized, valid)
        if len(self._pending) == self.shift:
            held, target = self._pending.popleft()
            # 不加止损时的持仓 = 同一条目标路径（向量化回测不加止损时的 held）
            self._unstopped = target if target is not None else _drift(self._unstopped, self._return_prev)
            unstopped_return = float(self._unstopped @ realized)
            self.equity *= 1.0 + float(held @ realized)
            self.unstopped_equity *= 1.0 + unstopped_return
            self.peak = max(self.peak, self.equity)
            self.high_water = max(self.high_water, self.equity)
            self.unstopped_path.append(self.unstopped_equity)
            self.unstopped_returns.append(unstopped_return)
            self._return_prev = realized
        return realized

    def _check_book(self, label: Hashable, holding: np.ndarray) -> Optional[str]:
        """熔断 / 恢复判断。返回 "trip"（这一步刚熔断）、"resume"（这一步刚恢复）或 None。"""
        rule = self.rules.book
        if rule.vol_mult is not None:
            dynamic = drawdown_limit(self.unstopped_returns, vol_mult=rule.vol_mult, vol_bars=rule.vol_bars)
            self.threshold = dynamic if np.isfinite(dynamic) else rule.max_drawdown
        drawdown = self.equity / self.peak - 1.0
        if not self.tripped and drawdown <= -self.threshold:
            self.tripped = True
            # 影子开端 = 这一根被平掉的实际持仓
            self.shadow = ShadowBook(holding, shift=self.shift, follow_targets=rule.shadow_follow_targets, label=label)
            self._market_at_trip = len(self.market)
            self._trip_threshold = self.threshold
            self._event(label, "book_trip", drawdown=drawdown)
            return "trip"
        if self.tripped and self.shadow.bars >= rule.min_flat_bars:
            ctx = ReentryContext(shadow=self.shadow, market=self.market, market_at_trip=self._market_at_trip,
                                 unstopped_path=self.unstopped_path, trip_threshold=self._trip_threshold)
            if rule.reentry.ready(ctx):
                self.tripped = False
                self.peak = self.equity
                self._event(label, "book_resume", drawdown=0.0)
                self.shadow = None  # 重新建仓，这段影子结束
                return "resume"
        return None

    def _apply_symbol_stops(
        self, close: np.ndarray, target: Optional[np.ndarray], held: np.ndarray, label: Hashable
    ) -> np.ndarray:
        rule = self.rules.symbol
        live = self._direction != 0
        with np.errstate(divide="ignore", invalid="ignore"):
            pnl = self._direction * (close / self._entry - 1.0)
        hit = live & np.isfinite(pnl) & (pnl <= -rule.stop_loss)
        for j in np.flatnonzero(hit):
            self._event(label, "symbol_stop", symbol=int(j), pnl=float(pnl[j]))
        self._locked_dir[hit] = self._direction[hit]
        self._locked |= hit
        if target is not None:  # 信号重置：目标里没有它了 / 方向翻转
            reset = self._locked & (np.sign(target) != self._locked_dir)
            self._locked &= ~reset
        held[self._locked] = 0.0
        opened = (held != 0) & (np.sign(held) != self._direction)
        self._entry[opened] = close[opened]
        self._direction[opened] = np.sign(held[opened])
        closed = held == 0
        self._direction[closed] = 0.0
        self._entry[closed] = np.nan
        return held

    def _reset_symbols(self) -> None:
        self._direction[:] = 0.0
        self._entry[:] = np.nan
        self._locked[:] = False

    def _event(self, label: Hashable, event: str, *, symbol: Any = None, drawdown: float = np.nan, pnl: float = np.nan) -> None:
        shadow = self.shadow
        self.events.append({"time": label, "event": event, "symbol": symbol, "equity": self.equity, "drawdown": drawdown,
                            "threshold": self.threshold, "total_drawdown": self.equity / self.high_water - 1.0,
                            "unstopped_equity": self.unstopped_equity,
                            "shadow_equity": np.nan if shadow is None else shadow.equity,
                            "shadow_rebound": np.nan if shadow is None else shadow.rebound,
                            "flat_bars": np.nan if shadow is None else shadow.bars, "pnl": pnl})
