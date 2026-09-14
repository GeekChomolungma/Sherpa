"""结果结构（设计文档 §8.4.4）：`AlphaCheckResult`（第一层）/ `BacktestResult`（第二层）。

向量化和事件驱动两条第二层路径共用同一个 `BacktestResult` 形状，方便交叉验证。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class AlphaCheckResult:
    ic_series: pd.Series
    ic_mean: float
    ic_std: float
    ic_ir: float
    quantile_returns: pd.DataFrame
    passed: bool


@dataclass(frozen=True)
class BacktestResult:
    equity_curve: pd.Series
    returns: pd.Series
    turnover: pd.Series
    sharpe: float
    calmar: float
    max_drawdown: float
