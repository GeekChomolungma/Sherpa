"""探索实验（`run_experiments.py`）的评估：跟关卡3 同一口径的扣费回测 + 打分诊断。

打分 → 目标仓位 → 回测 → 分段绩效这条链在 `sherpa.backtest.score_backtest`，跟关卡3（`research/friction_test/`）
共用同一份实现，口径从结构上一致：
- 打分 → 每期截面排名平移到 [-0.5, 0.5]（`cross_sectional_rank`，单因子配方权重 +1 时关卡3 的合成分数就是它）；
- 权重映射：Top-K 多空 + 排名迟滞，多空各 0.5，有效 symbol 不足 2k 的期空仓（`target_path`）；
- 回测：`run_vectorized_backtest`，`shift = 1 + 执行延迟`，每 N 根全仓调仓（`run_score_backtest`）；
- 成本：`research_config.json` 的 `costs`，净收益 = 毛收益 − 换手 × (手续费 + 滑点)（`cost_segment_rows`）。

这里只放探索特有的东西：
- 网格：关卡3 的网格 + 更宽的迟滞档位（`TOP_K_EXITS`）；
- 打分平滑（`smooth`）：对截面排名做逐 symbol 的指数平滑，用少量信号新鲜度换换手；
- 诊断（`diagnostics`）：RankIC、Pearson IC、首尾各 10 个的价差、打分对波动率（vol_42）的暴露；
- 多头腿 / 空头腿各自的贡献（`backtest(legs=True)`）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from sherpa.backtest.cost_model import FixedFeeCostModel, ZeroCostModel
from sherpa.backtest.score_backtest import (  # noqa: F401  cross_sectional_rank 供 run_experiments 用
    cost_segment_rows,
    cross_sectional_rank,
    run_score_backtest,
    target_path,
)
from sherpa.metrics.performance import annualized_return, sharpe_ratio

_COSTS = json.loads((Path(__file__).resolve().parents[1] / "research_config.json").read_text(encoding="utf-8"))["costs"]

# 关卡3 的网格（friction_test/config.py）
# 关卡3 原网格 + 探索时补的更宽迟滞（top20_exit80 / top30_exit90 / top30_exit150），看稳健区域的边界
TOP_K_EXITS: dict[int, tuple[int, ...]] = {10: (10, 20, 30, 50), 20: (20, 40, 60, 80, 100), 30: (90, 150)}
WEIGHTINGS: dict[str, dict[str, Any]] = {
    (f"top{k}" if exit_k == k else f"top{k}_exit{exit_k}"): {"method": "top_k", "k": k, "exit_k": exit_k}
    for k, exits in TOP_K_EXITS.items()
    for exit_k in exits
}
REBALANCE_EVERY: tuple[int, ...] = (1, 3, 6)
COST_MODELS = {
    "zero": ZeroCostModel(),
    "all_maker": FixedFeeCostModel(fee_bps=float(_COSTS["maker_fee_bps"]), slippage_bps=0.0),
    "all_taker": FixedFeeCostModel(fee_bps=float(_COSTS["taker_fee_bps"]), slippage_bps=float(_COSTS["taker_slippage_bps"])),
    "stress": FixedFeeCostModel(fee_bps=float(_COSTS["taker_fee_bps"]), slippage_bps=float(_COSTS["stress_slippage_bps"])),
}
BASE_COST = "all_taker"


def smooth(ranked: pd.DataFrame, halflife: float) -> pd.DataFrame:
    """逐 symbol 对截面排名做指数平滑（只用 <= t 的数据），原本是 NaN 的格子仍是 NaN。halflife=0 不平滑。"""
    if not halflife:
        return ranked
    return ranked.ewm(halflife=halflife, ignore_na=True).mean().where(ranked.notna())


def backtest(
    scores: pd.DataFrame, close: pd.DataFrame, interval: str, *, spec: Mapping[str, Any], rebalance_every: int, shift: int,
    segments: Mapping[str, pd.Series], periods_per_year: float, legs: bool = False,
) -> list[dict[str, Any]]:
    """一个 (映射, 调仓频率) 组合：零成本回测一次，再按每种成本假设扣费，分段统计（`sherpa.backtest.score_backtest`）。
    `legs=True` 时另外拆出多头 / 空头腿各自的零成本收益。"""
    targets = target_path(scores, spec, rebalance_every)
    gross, turnover = run_score_backtest(targets, close, interval, shift=shift, rebalance_every=rebalance_every)
    rows = cost_segment_rows(gross, turnover, COST_MODELS, segments, periods_per_year=periods_per_year)
    if legs:
        for leg, part in (("long", targets.clip(lower=0)), ("short", targets.clip(upper=0))):
            leg_gross, _ = run_score_backtest(part, close, interval, shift=shift, rebalance_every=rebalance_every)
            for segment, mask in segments.items():
                r = leg_gross[mask.reindex(leg_gross.index, fill_value=False)]
                rows.append({"cost_model": f"zero:{leg}_leg", "segment": segment,
                             "gross_sharpe": sharpe_ratio(r, periods_per_year=periods_per_year),
                             "net_ann_return": annualized_return(r, periods_per_year=periods_per_year)})
    return rows


def diagnostics(
    ranked: pd.DataFrame, label_1: pd.DataFrame, label_h: pd.DataFrame, vol: pd.DataFrame, segments: Mapping[str, pd.Series], k: int = 10,
) -> list[dict[str, Any]]:
    """每段：RankIC（下一根 / 训练标签的持有期）、Pearson IC、首尾各 k 个的价差（bps/期）、打分对 vol_42 的截面秩相关。"""
    def rank_corr(a: pd.DataFrame, b: pd.DataFrame) -> pd.Series:
        both = a.notna() & b.notna()
        return a.where(both).rank(axis=1).corrwith(b.where(both).rank(axis=1), axis=1)

    ric1 = rank_corr(ranked, label_1)
    rich = rank_corr(ranked, label_h)
    both = ranked.notna() & label_1.notna()
    pic1 = ranked.where(both).corrwith(label_1.where(both), axis=1)
    volx = rank_corr(ranked, vol)
    r = ranked.where(both).to_numpy()
    y = label_1.where(both).to_numpy()
    spread = np.full(len(ranked), np.nan)
    for i in range(len(ranked)):
        ok = np.isfinite(r[i]) & np.isfinite(y[i])
        if ok.sum() >= 2 * k:
            order = np.argsort(r[i][ok])
            yy = y[i][ok][order]
            spread[i] = yy[-k:].mean() - yy[:k].mean()
    spread = pd.Series(spread, index=ranked.index)
    rows = []
    for segment, mask in segments.items():
        m = mask.reindex(ranked.index, fill_value=False)
        s = lambda x: x[m].dropna()  # noqa: E731
        rows.append({
            "segment": segment,
            "rank_ic_1": s(ric1).mean(), "rank_ic_1_ir": s(ric1).mean() / s(ric1).std(),
            "rank_ic_h": s(rich).mean(), "rank_ic_h_ir": s(rich).mean() / s(rich).std(),
            "pearson_ic_1": s(pic1).mean(),
            f"spread_top{k}_bps": s(spread).mean() * 1e4,
            f"spread_top{k}_t": s(spread).mean() / s(spread).std() * np.sqrt(len(s(spread))),
            "vol42_exposure": s(volx).mean(),
        })
    return rows
