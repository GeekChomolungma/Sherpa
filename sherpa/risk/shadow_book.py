"""影子组合：一次组合熔断期间"如果没平仓会怎样"的理论账本，给恢复入场规则（`reentry.py`）提供依据。

生命周期跟一次熔断绑定：

```text
熔断（book_trip）── 拍下当时的实际持仓快照作为开端 ──► 每根 bar 用决策时刻已知的收盘价记账 ──► 恢复入场（book_resume）时结束
```

- **开端**：熔断那一根被平掉的持仓（漂移后的实际持仓），也就是"这次止损卖掉的东西"；
- **之后怎么持有**（`follow_targets`）：
  - `True`（默认，核心）：从快照出发，之后照常跟随目标路径调仓——"如果没熔断，策略这段时间会怎样"；
  - `False`（只留接口）：冻结快照，只随价格漂移、不调仓——"止损卖掉的那批仓位后来怎样了"。被策略抛弃的币会一直拖着
    影子净值，反映的不再是策略本身，容易永远等不到恢复，所以不作为恢复依据的主口径；
- **记账口径**跟 `StopController` 的组合净值相同：毛净值、晚 `shift` 根看到（第 k 步决策的持仓，在第 k + shift 步收到
  `close` 时记上它持有期的收益），只用决策时刻已知的价格，不偷看未来。

只依赖 numpy，跟 `sherpa.risk` 其余模块同一条包级约定。
"""

from __future__ import annotations

from collections import deque
from typing import Hashable, Optional

import numpy as np


def _drift(weights: np.ndarray, returns: np.ndarray) -> np.ndarray:
    """持仓按一根 bar 的收益漂移、保持总敞口不变（同 `sherpa.backtest.vectorized._drift` 口径）。"""
    gross = float(np.abs(weights).sum())
    if gross == 0.0:
        return weights.copy()
    value = weights * (1.0 + returns)
    total = float(np.abs(value).sum())
    return np.zeros_like(weights) if total == 0.0 else value / total * gross


class ShadowBook:
    """一次熔断的影子组合。由 `StopController` 在熔断时创建、恢复时丢弃；每根 bar 先 `settle()` 记账，再 `push()` 这一步的决策。"""

    def __init__(self, snapshot: np.ndarray, *, shift: int, follow_targets: bool = True, label: Hashable = None):
        snapshot = np.asarray(snapshot, dtype=float)
        self.shift = shift
        self.follow_targets = follow_targets
        self.start_label = label
        self.snapshot = snapshot.copy()
        # 待记账的决策：数组 = 那一步换成这个持仓，None = 那一步不调仓（上一步持仓随价格漂移）
        self._pending: deque[Optional[np.ndarray]] = deque([snapshot.copy()])
        self.weights = np.zeros_like(snapshot)   # 已记账的最近一步持仓
        self._return_prev = np.zeros_like(snapshot)
        self.equity = 1.0                        # 以开端为 1 的毛净值（已实现部分）
        self.peak = 1.0
        self.trough = 1.0
        self.path: list[float] = [1.0]           # 每次记账后的净值，path[0] 是开端
        self.bars = 0                            # 熔断后过了几根（push 的次数）

    def settle(self, realized: np.ndarray) -> None:
        """收到决策时刻的收盘价推出的已实现收益（`close[t_i] / close[t_{i−1}] − 1`），给 shift 步之前的那次决策记账。"""
        if len(self._pending) < self.shift:
            return
        decided = self._pending.popleft()
        self.weights = decided if decided is not None else _drift(self.weights, self._return_prev)
        self.equity *= 1.0 + float(self.weights @ realized)
        self.peak = max(self.peak, self.equity)
        self.trough = min(self.trough, self.equity)
        self.path.append(self.equity)
        self._return_prev = realized

    def push(self, target: Optional[np.ndarray]) -> None:
        """这一步的决策：调仓行传目标、非调仓行传 None。冻结模式下一律不调仓。"""
        self._pending.append(None if target is None or not self.follow_targets else np.asarray(target, dtype=float).copy())
        self.bars += 1

    # ---- 给恢复入场规则用的几个读数 -------------------------------------------------------------
    @property
    def change(self) -> float:
        """相对开端的涨跌。"""
        return self.equity - 1.0

    @property
    def drawdown(self) -> float:
        """相对熔断以来影子最高点的回撤（≤ 0）。"""
        return self.equity / self.peak - 1.0

    @property
    def rebound(self) -> float:
        """相对熔断以来影子最低点的反弹（≥ 0）。"""
        return self.equity / self.trough - 1.0
