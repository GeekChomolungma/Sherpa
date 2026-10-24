"""各后端训练共用的结果类型和小工具。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from dataset import TrainingFrame
from objective import ICIRObjective, period_starts


@dataclass
class FoldResult:
    files: list[str]
    best_iterations: list[int]
    metrics: dict[str, Any] = field(default_factory=dict)


def objective_for(frame: TrainingFrame, rows: slice, min_period_rows: int) -> ICIRObjective:
    return ICIRObjective(
        frame.y[rows], frame.weights[rows], period_starts(frame.times[rows].asi8), min_period_rows=min_period_rows
    )
