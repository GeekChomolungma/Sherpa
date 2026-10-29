"""止损控制：目标权重路径 → 逐期实际持仓（`held`）之间的一层，打分（alpha）始终不感知仓位和盈亏。

```text
alpha 打分 ─► 排名 ─► 目标权重路径 targets（无状态，`score_backtest.target_path`）
                              │
                              ▼  每根 bar：StopController.step(close, target, holding)
                         实际持仓 held ─► 回测引擎算换手 / 收益（研究线）、生成调仓意图（Runner）
```

对外是一个黑盒，守住三条，内部规则怎么升级都不影响调用方：

1. **只减风险**：输出相对基础仓位（调仓行 = 目标，非调仓行 = 漂移后的持仓）同号、绝对值不超过它——只会平仓 / 缩小，
   不开新仓、不加仓、不反手。选币永远是 alpha 和权重映射的事；
2. **因果**：触发判断只用决策时刻 t 已知的价格（`close`）。漂移后的持仓 `holding` 在 `shift > 1` 时已经用到了
   t 之后的收益（执行时刻的持仓），只当"保持不动"的基础仓位，不参与判断；
3. **规则全空 = 不干预**：输出等于原来的 `held`（调仓行 = 目标，非调仓行 = 漂移后的持仓）。

两类规则，组合熔断优先：

- **组合熔断**（`BookStop`）：组合净值相对峰值回撤到 `max_drawdown` 就把全部持仓平掉，进入熔断；熔断期间打分照常输出、
  目标照常算，只是不执行。**恢复**看影子组合——同一条目标路径、不加任何止损时的组合（就是 alpha 本来会怎么做）：
  熔断满 `min_flat_bars` 根、且影子净值重新站上它最近 `resume_bars` 根的均值，解除熔断，从下一个调仓行起按目标重新建仓；
  峰值重置为解除时的净值（否则离旧峰值还差 10%，一恢复就再次熔断）；
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
from dataclasses import asdict, dataclass
from typing import Any, Hashable, Optional

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BookStop:
    """组合熔断：毛净值相对峰值回撤到 `max_drawdown` 就全部平仓；影子净值站回均线后恢复。"""

    max_drawdown: float = 0.10     # 回撤 10% 熔断
    resume_bars: int = 42          # 恢复：影子净值站上最近 42 根（7 天）的均值
    min_flat_bars: int = 6         # 熔断后至少空仓 6 根（1 天）

    def __post_init__(self) -> None:
        if not 0 < self.max_drawdown < 1:
            raise ValueError(f"max_drawdown 要在 (0, 1) 之间，收到 {self.max_drawdown}")
        if self.resume_bars < 1 or self.min_flat_bars < 0:
            raise ValueError(f"resume_bars >= 1、min_flat_bars >= 0，收到 {self.resume_bars} / {self.min_flat_bars}")


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
        return {"book": None if self.book is None else asdict(self.book),
                "symbol": None if self.symbol is None else asdict(self.symbol)}

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "StopRules":
        book, symbol = raw.get("book"), raw.get("symbol")
        return cls(book=None if book is None else BookStop(**book), symbol=None if symbol is None else SymbolStop(**symbol))


def _drift(weights: np.ndarray, returns: np.ndarray) -> np.ndarray:
    """持仓按一根 bar 的收益漂移、保持总敞口不变（同 `sherpa.backtest.vectorized._drift` 口径）。"""
    gross = float(np.abs(weights).sum())
    if gross == 0.0:
        return weights.copy()
    value = weights * (1.0 + returns)
    total = float(np.abs(value).sum())
    return np.zeros_like(weights) if total == 0.0 else value / total * gross


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
        self._shadow = np.zeros(n)               # 已记账的最近一步的影子持仓
        self.equity = 1.0                        # 组合毛净值（已实现部分）
        self.peak = 1.0
        self.shadow_equity = 1.0
        self._shadow_window: deque[float] = deque(maxlen=rules.book.resume_bars if rules.book else 1)
        self.tripped = False
        self._tripped_at = 0
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

        self._settle(close)
        if self.rules.book is not None:
            self._check_book(label)
        if self.tripped:
            held = np.zeros_like(base)
            self._reset_symbols()
        else:
            held = base.copy()
            if self.rules.symbol is not None:
                held = self._apply_symbol_stops(close, target, held, label)
        self._pending.append((held.copy(), None if target is None else target.copy()))
        self._close_prev = close
        self._step += 1
        return held

    def events_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.events, columns=["time", "event", "symbol", "equity", "drawdown", "shadow_equity", "pnl"])

    # ------------------------------------------------------------------------------------------
    def _settle(self, close: np.ndarray) -> None:
        """记账：这一步得知的已实现收益 = 第 step−shift 步决策的持仓在它持有期里的收益。"""
        if self._close_prev is None:
            realized = np.zeros_like(close)
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                realized = close / self._close_prev - 1.0
            realized = np.where(np.isfinite(realized), realized, 0.0)
        if len(self._pending) == self.shift:
            held, target = self._pending.popleft()
            # 影子持仓 = 同一条目标路径、不加止损时的持仓（向量化回测不加止损时的 held）
            self._shadow = target if target is not None else _drift(self._shadow, self._return_prev)
            self.equity *= 1.0 + float(held @ realized)
            self.shadow_equity *= 1.0 + float(self._shadow @ realized)
            self.peak = max(self.peak, self.equity)
            self._shadow_window.append(self.shadow_equity)
            self._return_prev = realized

    def _check_book(self, label: Hashable) -> None:
        rule = self.rules.book
        drawdown = self.equity / self.peak - 1.0
        if not self.tripped and drawdown <= -rule.max_drawdown:
            self.tripped, self._tripped_at = True, self._step
            self._event(label, "book_trip", drawdown=drawdown)
        elif self.tripped and self._step - self._tripped_at >= rule.min_flat_bars:
            window = self._shadow_window
            if len(window) == window.maxlen and self.shadow_equity > float(np.mean(window)):
                self.tripped = False
                self.peak = self.equity
                self._event(label, "book_resume", drawdown=0.0)

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
        self.events.append({"time": label, "event": event, "symbol": symbol, "equity": self.equity,
                            "drawdown": drawdown, "shadow_equity": self.shadow_equity, "pnl": pnl})
