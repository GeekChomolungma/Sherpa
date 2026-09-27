"""关卡3 用的纯函数：按冻结配方重建合成分数、分数 → 目标权重路径（含换手缓冲带）、分段绩效统计。

合成部分（`cross_sectional_rank` / `weighted_composite` / 路由）从 `research/factor_synthesis/signals.py`
拷贝后独立维护（research 子项目之间不互相 import），口径必须跟关卡2 保持一致：关卡3 回测的就是关卡2
在验证段上比较过的那个分数，差一点就不是同一个信号了。不同的是**权重不再在这里估计**——方向、权重
都已经由关卡2 在选择段上估好、经 `refresh_candidates.py` 写进 `config.CASES`，这里只照配方复现。

矩阵约定跟 sherpa 其余部分一致：`(T, N)` DataFrame，行 = bar 时间，列 = symbol。
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np
import pandas as pd

from sherpa.metrics.performance import (
    annualized_return,
    calmar_ratio,
    equity_curve,
    max_drawdown,
    sharpe_ratio,
    turnover_decay,
)
from sherpa.portfolio.buffer import no_trade_band, top_k_hysteresis
from sherpa.portfolio.weighting import demean_l1


# ---------------------------------------------------------------------------
# 按配方重建合成分数（口径同关卡2）
# ---------------------------------------------------------------------------

def cross_sectional_rank(scores: pd.DataFrame) -> pd.DataFrame:
    """逐期截面百分位排名，平移到 [-0.5, 0.5]。跟关卡2 同名函数一致。"""
    return scores.rank(axis=1, pct=True) - 0.5


def weighted_composite(ranked: Mapping[str, pd.DataFrame], weights: Mapping[str, float]) -> pd.DataFrame:
    """`Σ_i w_i × rank_i / Σ_i |w_i|`，逐 (bar, symbol) 只对当期有值的因子求和、归一。跟关卡2 同名函数一致。

    `weights` 带符号：符号是方向，绝对值是权重大小；等权方案就是 `w_i = ±1`。
    """
    used = [name for name, weight in weights.items() if weight != 0.0]
    if not used:
        raise ValueError(f"配方里没有权重非 0 的因子：{dict(weights)}")
    total = None
    norm = None
    for name in used:
        weight = weights[name]
        contribution = ranked[name] * weight
        total = contribution.fillna(0.0) if total is None else total.add(contribution.fillna(0.0), fill_value=0.0)
        present = ranked[name].notna().astype(float) * abs(weight)
        norm = present if norm is None else norm.add(present, fill_value=0.0)
    return total.where(norm > 0) / norm.where(norm > 0)


def case_scores(case: Mapping[str, Any], ranked: Mapping[str, pd.DataFrame], regime: pd.DataFrame) -> pd.DataFrame:
    """按 `config.CASES` 里一个 case 的配方算出合成分数。

    - `kind="static"`：全程同一组权重（G0 / L1 / L0 / 单因子参照）；
    - `kind="routed"`：每根 bar 按它所处的 `dimension` state 选那个 state 的权重；state 未知（滚动窗口
      warm-up）或该 state 没有配方时退回 `fallback` 的权重——跟关卡2 `routed_composite` 的规则一致。
      regime 标签是 point-in-time 的（滚动分位数只看 <= t 的数据），路由不引入未来信息。
    """
    if case["kind"] == "static":
        return weighted_composite(ranked, case["weights"])
    if case["kind"] != "routed":
        raise ValueError(f"未知的 case kind：{case['kind']!r}")

    result = weighted_composite(ranked, case["fallback"])
    labels = regime[case["dimension"]]
    for state, weights in case["states"].items():
        if not any(w != 0.0 for w in weights.values()):
            continue
        rows = (labels == state).fillna(False).reindex(result.index, fill_value=False)
        if not rows.any():
            continue
        result.loc[rows] = weighted_composite(ranked, weights).loc[rows]
    return result


def required_factors(cases: Mapping[str, Mapping[str, Any]]) -> list[str]:
    """所有 case 用到的因子并集（按首次出现顺序去重），决定要算哪些因子的残差分数。"""
    seen: dict[str, None] = {}
    for case in cases.values():
        groups = [case["weights"]] if case["kind"] == "static" else [case["fallback"], *case["states"].values()]
        for weights in groups:
            for name in weights:
                seen.setdefault(name, None)
    return list(seen)


# ---------------------------------------------------------------------------
# 分数 -> 目标权重
# ---------------------------------------------------------------------------

def target_path(scores: pd.DataFrame, spec: Mapping[str, Any], rebalance_every: int) -> pd.DataFrame:
    """按时间顺序把合成分数变成目标权重路径，**总敞口统一为 1**（多空各 0.5）。

    `spec` 是 `config.WEIGHTINGS` 里的一项：
    - `{"method": "demean_l1", "band": b}`：按分数配权；`band > 0` 时叠加逐 symbol 不交易带
      （`sherpa.portfolio.buffer.no_trade_band`）；
    - `{"method": "top_k", "k": k, "exit_k": e}`：Top-K 多空；`exit_k > k` 时叠加排名迟滞
      （`sherpa.portfolio.buffer.top_k_hysteresis`，排进前 k 开仓、跌出前 exit_k 才平仓）。

    `rebalance_every=N`：每 N 根 bar 把整个组合换成最新目标（全仓调仓），中间不交易。

    缓冲带带状态（参考上一期目标），所以只能逐期顺序计算。只在调仓行（第 0、N、2N…… 行，跟
    `run_vectorized_backtest(rebalance_every=N)` 同一口径）算目标，状态也只在调仓行之间传递；非调仓行
    填 0，回测不会用到它们。

    `demean_l1` 本来就是 L1=1；Top-K 是多头 +1、空头 -1（L1=2），除以 2 对齐，否则不同映射方式的收益、
    换手、成本不在同一个杠杆上。有效 symbol 不足 `2k` 的 bar 空仓（全 0），空仓 bar 的占比见结果表的
    `flat_bar_fraction` 列。
    """
    method = spec["method"]
    if method == "demean_l1":
        band = float(spec.get("band", 0.0))

        def step(alpha: pd.Series, prev: pd.Series | None) -> pd.Series:
            return no_trade_band(demean_l1(alpha), prev, band)
    elif method == "top_k":
        k = int(spec["k"])
        exit_k = int(spec.get("exit_k", k))

        def step(alpha: pd.Series, prev: pd.Series | None) -> pd.Series:
            if alpha.notna().sum() < 2 * k:
                return pd.Series(0.0, index=alpha.index)
            return top_k_hysteresis(alpha, prev, k, exit_k) / 2.0  # 迟滞只看上一期的多空方向，不看权重大小
    else:
        raise ValueError(f"未知的权重映射方式：{method!r}")

    values = np.zeros(scores.shape)
    prev: pd.Series | None = None
    for i in range(0, len(scores.index), rebalance_every):
        target = step(scores.iloc[i], prev).reindex(scores.columns).fillna(0.0)
        values[i] = target.to_numpy()
        prev = target
    return pd.DataFrame(values, index=scores.index, columns=scores.columns)


# ---------------------------------------------------------------------------
# 分段绩效
# ---------------------------------------------------------------------------

def segment_stats(
    gross: pd.Series,
    turnover: pd.Series,
    net: pd.Series,
    *,
    periods_per_year: float,
) -> dict[str, float]:
    """一段区间（已经切好）内的扣费前后绩效。三条序列同 index：逐 bar 毛收益、换手、净收益。

    - `breakeven_cost_bps`：单边成本（手续费 + 滑点）涨到多少 bps，这段的平均净收益刚好归零
      = 平均毛收益 / 平均换手。比较"离红线还有多远"时比单一成本假设下的 Sharpe 更直观；
    - `turnover_decay`：`1 - 净累计收益 / 毛累计收益`，成本吃掉了毛利的多大比例
      （`sherpa.metrics.performance.turnover_decay`；毛累计收益 <= 0 时为 NaN）；
    - `flat_bar_fraction`：毛收益、换手都为 0 的 bar 占比（warm-up、Top-K 有效 symbol 不足而空仓等），
      占比高说明这段的 Sharpe 是在很少的交易 bar 上算出来的。
    """
    net_curve = equity_curve(net)
    mean_turnover = float(turnover.mean()) if len(turnover) else float("nan")
    mean_gross = float(gross.mean()) if len(gross) else float("nan")
    cost = gross - net
    return {
        "bars": int(len(net)),
        "gross_sharpe": sharpe_ratio(gross, periods_per_year=periods_per_year),
        "net_sharpe": sharpe_ratio(net, periods_per_year=periods_per_year),
        "gross_ann_return": annualized_return(gross, periods_per_year=periods_per_year),
        "net_ann_return": annualized_return(net, periods_per_year=periods_per_year),
        "net_ann_vol": float(net.std() * periods_per_year**0.5) if len(net) > 1 else float("nan"),
        "net_max_drawdown": max_drawdown(net_curve),
        "net_calmar": calmar_ratio(net, periods_per_year=periods_per_year),
        "turnover_per_bar": mean_turnover,
        "turnover_per_year": mean_turnover * periods_per_year,
        "cost_drag_per_year": float(cost.mean() * periods_per_year) if len(cost) else float("nan"),
        "turnover_decay": turnover_decay(gross, net),
        "breakeven_cost_bps": mean_gross / mean_turnover * 10_000.0 if mean_turnover > 0 else float("nan"),
        "flat_bar_fraction": float(((gross == 0.0) & (turnover == 0.0)).mean()) if len(net) else float("nan"),
    }


def segment_masks(index: pd.DatetimeIndex, validation_start: pd.Timestamp) -> dict[str, pd.Series]:
    """把研究段切成选择段 / 验证段两个布尔掩码，按**决策时点**切。

    回测结果的第 t 行是 t 时刻决策的持仓赚到的收益（`run_vectorized_backtest` 的时间标签口径），跟关卡2
    IC 序列的第 t 行（t 时刻的分数 vs 它的未来收益标签）是同一个时点，所以两关按同一个 `validation_start`
    切出来的是同一批决策。

    跟关卡2 不同，这里不 purge 边界：关卡2 的 purge 是为了不让"估方向用的标签"伸进验证段；关卡3 不在
    任何一段上估参数，配方在跑回测之前就已冻结，两段只是分开统计同一条连续的持仓路径。
    """
    in_validation = pd.Series(index >= validation_start, index=index)
    return {"selection(样本内参考)": ~in_validation, "validation(方案比较)": in_validation}

