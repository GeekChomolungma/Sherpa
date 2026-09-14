"""手续费/滑点模型（设计文档 §8.4.3）：向量化和事件驱动两条第二层路径共用同一套实现。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class CostModel(Protocol):
    def cost(self, turnover: float) -> float: ...


@dataclass(frozen=True)
class FixedFeeCostModel:
    """`turnover * (手续费 + 滑点)`，两者都用 bps（万分之一）表示。"""

    fee_bps: float
    slippage_bps: float = 0.0

    def cost(self, turnover: float) -> float:
        return turnover * (self.fee_bps + self.slippage_bps) / 10_000.0


@dataclass(frozen=True)
class ZeroCostModel:
    """零成本模型：研究/测试时用来跟真实成本模型的结果对比（gross vs net）。"""

    def cost(self, turnover: float) -> float:
        return 0.0
