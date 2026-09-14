"""第二层·真实可变现性验证的绩效指标（`docs/backtest_principle.md` 二、2(5)）。

每个函数只吃一条收益率 `pd.Series`，不关心它是回测模拟出来的还是别处来的——这条边界是
刻意设计的（设计文档 §8.2 决策3），为的是让这套公式将来能被 Sherpa 之外的地方复用。
"""

from __future__ import annotations

import math

import pandas as pd


def equity_curve(returns: pd.Series, initial_capital: float = 1.0) -> pd.Series:
    """净值曲线：缺失的收益率按 0 处理（该期没有交易/没有数据，净值不变）。"""
    return initial_capital * (1.0 + returns.fillna(0.0)).cumprod()


def annualized_return(returns: pd.Series, *, periods_per_year: float) -> float:
    """把样本期的复合增长率外推成年化收益率。

    在对数空间里算指数，而不是直接 `total_growth ** (periods_per_year / n)`——分钟级数据
    在样本很短时指数会被放得极大（比如 4 根 1m bar 外推到 `periods_per_year=525600`），
    直接乘方会触发 `OverflowError` 而不是给出一个"这个数很离谱但至少不崩溃"的结果。
    """
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    total_growth = float((1.0 + clean).prod())
    if total_growth <= 0:
        return -1.0
    exponent = periods_per_year / len(clean)
    try:
        return float(math.exp(math.log(total_growth) * exponent) - 1.0)
    except OverflowError:
        return float("inf")


def sharpe_ratio(returns: pd.Series, *, periods_per_year: float, risk_free_rate: float = 0.0) -> float:
    """年化 Sharpe。`risk_free_rate` 是年化无风险利率，按 `periods_per_year` 换算成单期再扣减。"""
    clean = returns.dropna()
    if clean.empty:
        return float("nan")
    excess = clean - risk_free_rate / periods_per_year
    std = float(excess.std())
    # 用绝对容差而不是 `== 0`：同样是 sherpa.metrics.factor.ic_summary 踩过的浮点误差坑
    # （一组理论上完全相等的收益率，算出来的 std 可能是 ~1e-17 而不是精确的 0）。
    if std <= 1e-9:
        return float("nan")
    return float(excess.mean() / std * (periods_per_year**0.5))


def max_drawdown(equity: pd.Series) -> float:
    """最大回撤，负数（比如 -0.23 表示回撤 23%）。空序列返回 NaN。"""
    if equity.empty:
        return float("nan")
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return float(drawdown.min())


def calmar_ratio(returns: pd.Series, *, periods_per_year: float) -> float:
    """年化收益 / |最大回撤|。最大回撤为 0（比如全程没有任何波动）时定义为 NaN。"""
    mdd = max_drawdown(equity_curve(returns))
    if mdd == 0.0 or pd.isna(mdd):
        return float("nan")
    return float(annualized_return(returns, periods_per_year=periods_per_year) / abs(mdd))


def turnover_decay(gross_returns: pd.Series, net_returns: pd.Series) -> float:
    """成本对总收益的侵蚀比例：`1 - net累计收益 / gross累计收益`。

    原理文档只在指标列表里提到"换手衰减率"这个名字，没有给出唯一的权威公式——这是本仓库
    对它的操作化定义：值越接近 1，说明换手摩擦吃掉了越大比例的原始 alpha 边际；`gross` 累计
    收益为 0 或负数时该定义没有意义，返回 NaN。
    """
    gross_total = float(equity_curve(gross_returns).iloc[-1] - 1.0) if len(gross_returns) else float("nan")
    net_total = float(equity_curve(net_returns).iloc[-1] - 1.0) if len(net_returns) else float("nan")
    if pd.isna(gross_total) or gross_total <= 0:
        return float("nan")
    return float(1.0 - net_total / gross_total)
