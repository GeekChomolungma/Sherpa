"""持仓漂移与换手率（`docs/backtest_principle.md` §2(4)）。

不是回测专属——未来实盘要做"持仓偏离目标仓位超过阈值才触发再平衡"的监控，同样可以直接
复用这两个函数（设计文档 §8.3 决策2 / §8.5）。
"""

from __future__ import annotations

import pandas as pd


def drift_weights(prev_weights: pd.Series, period_returns: pd.Series) -> pd.Series:
    """把上一期权重按本期实际价格变动漂移成 `W_drift`，并保持总杠杆（L1 范数）不变。

    `prev_weights`/`period_returns` 按 symbol 对齐（外连接，缺失按 0 处理：没有旧仓位的
    symbol 视为 0 权重，没有收益数据的 symbol 视为本期收益 0）。总敞口为 0（比如上一期就是
    空仓）时直接原样返回，不做除零运算。
    """
    prev_weights, period_returns = prev_weights.align(period_returns, join="outer", fill_value=0.0)
    gross_exposure = float(prev_weights.abs().sum())
    if gross_exposure == 0.0:
        return prev_weights.copy()
    drifted_value = prev_weights * (1.0 + period_returns.fillna(0.0))
    drifted_exposure = float(drifted_value.abs().sum())
    if drifted_exposure == 0.0:
        return pd.Series(0.0, index=prev_weights.index)
    return drifted_value / drifted_exposure * gross_exposure


def turnover(new_weights: pd.Series, drifted_weights: pd.Series) -> float:
    """真实换手率：`sum(abs(W_new - W_drift))`，按 symbol 对齐（外连接，缺失按 0 处理）。"""
    new_weights, drifted_weights = new_weights.align(drifted_weights, join="outer", fill_value=0.0)
    return float((new_weights - drifted_weights).abs().sum())
