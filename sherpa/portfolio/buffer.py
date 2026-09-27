"""换手缓冲带：`(本期 alpha / 目标, 上一期目标) -> 本期目标`（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` 关卡2 第 3 条
"平滑过渡约束"、关卡3 摩擦测试）。

跟 `weighting.py` 的区别是**带状态**：本期目标要参考上一期目标，边界附近的小幅变动不交易，用少量
信号新鲜度换大幅降低的换手。状态由调用方持有、显式传入，函数本身仍是纯函数——回测按时间顺序逐期
调用，实盘在 `BaseStrategy.on_bar` 里记住上一期的目标再调用，两边用的是同一个函数（设计文档 §8.3
决策1：会改变决策结果的逻辑不允许回测、实盘各写一份）。

状态为什么是"上一期目标"而不是"当前实际持仓"：执行有延迟（信号在 t 收盘算出，晚 `delay` 根 bar
才成交），做决策时上一期的单可能还没成交，实际持仓并不确定；上一期目标则是决策时点确定已知的，
回测和实盘都拿得到，口径一致。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def top_k_hysteresis(alpha: pd.Series, prev_target: pd.Series | None, k: int, exit_k: int) -> pd.Series:
    """Top-K 多空 + 排名迟滞：排进前 `k` 名才开仓，跌出前 `exit_k` 名才平仓（`exit_k >= k`）。

    多头腿：上一期的多头里、本期排名仍在前 `exit_k` 名的继续持有（按本期排名从高到低，最多 `k` 个），
    空出来的名额按本期排名从高到低补足到 `k` 个；空头腿对称（按排名从低到高）。两条腿各 `k` 个，
    权重 `+1/k` / `-1/k`，跟 `top_k_long_short` 同一口径——`exit_k == k` 时结果与它完全相同。

    本期 alpha 缺失的 symbol（下架、不可交易）一律平仓，不参与排名。同一个 symbol 不会同时出现在
    两条腿里：空头腿从多头腿选剩的 symbol 里选。有效 symbol 不足 `2k` 时抛 `ValueError`，跟
    `top_k_long_short` 一致。
    """
    if k <= 0:
        raise ValueError(f"k 必须是正整数，实际是 {k!r}")
    if exit_k < k:
        raise ValueError(f"exit_k 不能小于 k（exit_k={exit_k!r}, k={k!r}）")
    values = alpha.to_numpy(dtype=float)
    valid = np.flatnonzero(~np.isnan(values))
    if len(valid) < 2 * k:
        raise ValueError(f"top_k_hysteresis(k={k}) 需要至少 {2 * k} 个有效 symbol，实际只有 {len(valid)} 个")

    # 按 numpy 数组实现（每个截面几百个 symbol、回测要逐期调用上万次）。排序口径等价于
    # `alpha.dropna().sort_values(ascending=False, kind="stable")`：分数相同按原顺序。
    descending = valid[np.argsort(-values[valid], kind="stable")]
    if prev_target is not None:
        prev = prev_target.reindex(alpha.index).fillna(0.0).to_numpy(dtype=float)
    else:
        prev = np.zeros(len(values))

    longs = _pick_leg(descending, prev > 0, k, exit_k)
    taken = np.zeros(len(values), dtype=bool)
    taken[longs] = True
    ascending = descending[::-1]
    shorts = _pick_leg(ascending[~taken[ascending]], prev < 0, k, exit_k)

    weights = np.zeros(len(values))
    weights[longs] = 1.0 / k
    weights[shorts] = -1.0 / k
    return pd.Series(weights, index=alpha.index)


def _pick_leg(order: np.ndarray, held: np.ndarray, k: int, exit_k: int) -> np.ndarray:
    """一条腿：`order` 里排在前 `exit_k` 的已持仓 symbol 优先保留（最多 k 个），再按 `order` 顺序补足到 k 个。"""
    keep = order[:exit_k][held[order[:exit_k]]][:k]
    kept = np.zeros(len(held), dtype=bool)
    kept[keep] = True
    fill = order[~kept[order]][: k - len(keep)]
    return np.concatenate([keep, fill])


def no_trade_band(target: pd.Series, prev_target: pd.Series | None, band: float) -> pd.Series:
    """逐 symbol 的不交易带：本期目标跟上一期目标相差不超过 `band`（权重绝对值）就维持上一期目标。

    用在按分数配权（`demean_l1`）这类连续权重上：几百个 symbol 的权重每期都会有细小变动，每一笔都
    去交易，成本远超这些小调整带来的收益。`band=0` 等于不设缓冲，直接返回 `target`。

    注意：只有部分 symbol 调整时，多空两边不再严格对称、总敞口也会偏离 1 一点（偏差不超过
    `band × 被冻结的 symbol 数`）。这里刻意不重新归一——一归一，所有被冻结的权重又都会跟着变，
    缓冲带就失效了。
    """
    if band < 0:
        raise ValueError(f"band 不能为负，收到 {band!r}")
    if prev_target is None or band == 0:
        return target.copy()
    prev, target = prev_target.align(target, join="outer", fill_value=0.0)
    within = (target - prev).abs() <= band
    return prev.where(within, target)
