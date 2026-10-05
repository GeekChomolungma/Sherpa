"""多因子打分 → 合成 → 目标仓位 → 扣费回测 → 分段绩效：研究流水线关卡2（`research/factor_synthesis/`）、
关卡3（`research/friction_test/`）和 ML 探索实验（`research/ml_training/evaluation.py`）共用的一条链。

以前截面排名、加权合成在关卡2、关卡3 各有一份，回测和分段统计在关卡3 和探索实验各有一份，口径只能靠人工核对。
现在只在这里定义，调用方只负责"因子 / 方向 / 权重从哪来"（关卡2：在选择段上估；关卡3：读冻结配方；探索实验：直接给
打分矩阵）和"网格 / 成本取哪些"（各自的 config）。

```text
各因子打分 (T, N)
  │ cross_sectional_rank       每期截面排名，平移到 [-0.5, 0.5]
  │ weighted_composite         带符号权重加权合成：Σ w_i·rank_i / Σ|w_i|（单因子 +1 时就是它自己的排名）
  │ target_path                逐个调仓行：打分 → 目标权重（Top-K + 排名迟滞 / demean_l1 + 不交易带），总敞口 1
  │ run_vectorized_backtest    漂移、换手、逐 bar 毛收益（零成本跑一次）
  │ cost_segment_rows          每种成本假设：净收益 = 毛收益 − 成本(换手)；按段切开算 segment_stats
  ▼
分段绩效（一行 = 成本假设 × 段）
```

成本只从收益里扣、不影响仓位（权重是资金占比），所以"零成本跑一次再按成本扣"跟直接用该成本模型跑回测结果相同，
省掉每种成本各跑一遍逐 bar 递推。

矩阵约定跟 sherpa 其余部分一致：`(T, N)` DataFrame，行 = bar 时间，列 = symbol。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

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

from .cost_model import CostModel, ZeroCostModel
from .vectorized import run_vectorized_backtest


def cross_sectional_rank(scores: pd.DataFrame) -> pd.DataFrame:
    """逐期截面百分位排名，平移到 [-0.5, 0.5]（截面中位数约为 0）。NaN 不参与排名、保持 NaN。

    为什么合成前必须先做这一步：不同因子的原始分数量级、分布差别极大（有的是秩，有的是价格比率），
    直接相加等于让量级最大的那个因子独占权重。换成截面排名后，每个因子在每一期都落在同一个尺度上，
    "等权"才名副其实。用排名而不是 z-score，是为了不让少数极端值主导。
    """
    return scores.rank(axis=1, pct=True) - 0.5


def weighted_composite(
    ranked: Mapping[str, pd.DataFrame],
    weights: Mapping[str, float],
    factors: Optional[Sequence[str]] = None,
) -> pd.DataFrame:
    """加权合成：`Σ_i w_i × rank_i / Σ_i |w_i|`，逐 (bar, symbol) 只对当期有值的因子求和、归一。

    `ranked` 是各因子已经做过 `cross_sectional_rank` 的打分。`weights` 是**带符号**的权重：符号就是方向
    （+1 原方向 / −1 反向使用），绝对值是权重大小；等权合成就是 `w_i = ±1`。`factors` 指定参与合成的因子
    （关卡2：候选名单），不给就用 `weights` 里的全部（关卡3：冻结配方）；求和按这个顺序进行。

    某个 symbol 在某一期缺了部分因子（比如刚上线、窗口还没攒够），就只用它有值的那几个因子，
    分母也只累加这几个因子的 |w_i|，而不是整格丢掉；一个因子都没有才是 NaN。权重为 0 的因子不参与。
    """
    candidates = list(weights) if factors is None else list(factors)
    used = [name for name in candidates if weights.get(name, 0.0) != 0.0]
    if not used:
        raise ValueError(f"没有可用于合成的因子（候选 {candidates} 的权重全部为 0）：{dict(weights)}")
    total = None
    norm = None
    for name in used:
        weight = weights[name]
        contribution = ranked[name] * weight
        total = contribution.fillna(0.0) if total is None else total.add(contribution.fillna(0.0), fill_value=0.0)
        present = ranked[name].notna().astype(float) * abs(weight)
        norm = present if norm is None else norm.add(present, fill_value=0.0)
    return total.where(norm > 0) / norm.where(norm > 0)


def target_path(scores: pd.DataFrame, spec: Mapping[str, Any], rebalance_every: int) -> pd.DataFrame:
    """按时间顺序把打分变成目标权重路径，**总敞口统一为 1**（多空各 0.5）。

    `spec` 是一种权重映射：
    - `{"method": "demean_l1", "band": b}`：按分数配权；`band > 0` 时叠加逐 symbol 不交易带
      （`sherpa.portfolio.buffer.no_trade_band`）；
    - `{"method": "top_k", "k": k, "exit_k": e}`：Top-K 多空；`exit_k > k` 时叠加排名迟滞
      （`sherpa.portfolio.buffer.top_k_hysteresis`，排进前 k 开仓、跌出前 exit_k 才平仓）。

    `rebalance_every=N`：每 N 根 bar 把整个组合换成最新目标（全仓调仓），中间不交易。

    缓冲带带状态（参考上一期目标），所以只能逐期顺序计算。只在调仓行（第 0、N、2N…… 行，跟
    `run_vectorized_backtest(rebalance_every=N)` 同一口径）算目标，状态也只在调仓行之间传递；非调仓行
    填 0，回测不会用到它们。

    `demean_l1` 本来就是 L1=1；Top-K 是多头 +1、空头 -1（L1=2），除以 2 对齐，否则不同映射方式的收益、
    换手、成本不在同一个杠杆上。有效 symbol 不足 `2k` 的 bar 空仓（全 0），空仓 bar 的占比见
    `segment_stats` 的 `flat_bar_fraction`。
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


@dataclass(frozen=True)
class _Prices:
    """`run_vectorized_backtest` 只用到 `close` 和 `interval`；完整 BarPanel 有十来个字段，发给多进程 worker 太大。"""

    close: pd.DataFrame
    interval: str


def run_score_backtest(
    targets: pd.DataFrame, close: pd.DataFrame, interval: str, *, shift: int, rebalance_every: int
) -> tuple[pd.Series, pd.Series]:
    """目标权重路径 → (逐 bar 毛收益, 逐 bar 换手)，零成本。目标权重已经按调仓行算好，回测只做恒等映射。"""
    result = run_vectorized_backtest(
        targets, _Prices(close, interval), lambda row: row, ZeroCostModel(), shift=shift, rebalance_every=rebalance_every
    )
    return result.returns, result.turnover


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


def cost_segment_rows(
    gross: pd.Series,
    turnover: pd.Series,
    cost_models: Mapping[str, CostModel],
    segments: Mapping[str, pd.Series],
    *,
    periods_per_year: float,
    net_curves: Optional[dict[tuple[str, str], pd.Series]] = None,
) -> list[dict[str, Any]]:
    """每种成本假设 × 每段：`{"cost_model", "segment", **segment_stats}` 一行。

    `segments` 是 {段名: 布尔 Series}（按决策时点切，index 跟回测结果对齐，缺的行当 False）。传了 `net_curves` 时，
    顺手把每个 (成本, 段) 的逐 bar 净收益存进去，调用方要画净值曲线时用。
    """
    rows = []
    for cost_name, cost_model in cost_models.items():
        net = gross - turnover.map(cost_model.cost)
        for segment, in_segment in segments.items():
            in_rows = in_segment.reindex(net.index, fill_value=False)
            rows.append({
                "cost_model": cost_name,
                "segment": segment,
                **segment_stats(gross[in_rows], turnover[in_rows], net[in_rows], periods_per_year=periods_per_year),
            })
            if net_curves is not None:
                net_curves[(cost_name, segment)] = net[in_rows]
    return rows
