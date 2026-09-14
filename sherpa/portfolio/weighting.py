"""alpha 分数 -> 目标权重（`docs/backtest_principle.md` §2(2)）。

每个函数的签名统一是"一个截面的 alpha 分数 `pd.Series`（index=symbol）-> 一个截面的目标
权重 `pd.Series`"，纯函数、无状态——同一个函数在回测第二层和 `BaseStrategy.on_bar()` 里
调用，产出的权重口径必须完全一致（设计文档 §8.3 决策1）。
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def demean_l1(alpha: pd.Series) -> pd.Series:
    """截面去均值（Dollar Neutral）+ L1 归一化（Leverage Constraint）。

    `sum(weights) == 0`（多空对称）且 `sum(abs(weights)) == 1`（除非全部 alpha 相同导致
    去均值后全 0，此时返回全 0 权重，不强行分配杠杆）。缺失的 symbol 权重为 0。
    """
    valid = alpha.dropna()
    if valid.empty:
        return pd.Series(0.0, index=alpha.index)
    demeaned = valid - valid.mean()
    l1_norm = demeaned.abs().sum()
    weights = demeaned / l1_norm if l1_norm != 0 else pd.Series(0.0, index=valid.index)
    return weights.reindex(alpha.index, fill_value=0.0)


def top_k_long_short(alpha: pd.Series, k: int) -> pd.Series:
    """Top-K 分位数离散映射：多头组均匀分配 `+1/k`，空头组分配 `-1/k`，其余为 0。

    需要至少 `2k` 个非缺失 symbol 才能同时凑出两条腿，否则抛 `ValueError`——静默截断成
    重叠的多空组会产出没有意义的权重，比报错更危险。
    """
    if k <= 0:
        raise ValueError(f"k 必须是正整数，实际是 {k!r}")
    valid = alpha.dropna()
    if len(valid) < 2 * k:
        raise ValueError(f"top_k_long_short(k={k}) 需要至少 {2 * k} 个有效 symbol，实际只有 {len(valid)} 个")
    ranked = valid.sort_values(ascending=False)
    weights = pd.Series(0.0, index=alpha.index)
    weights.loc[ranked.index[:k]] = 1.0 / k
    weights.loc[ranked.index[-k:]] = -1.0 / k
    return weights


def equal_weight(alpha: pd.Series) -> pd.Series:
    """基线映射：按 alpha 符号等权多空，不看分数大小——用作跟其他映射方式的对照基准。

    每个非缺失、非零 symbol 分到 `sign(alpha) / n` 的权重，`n` 是非缺失 symbol 数。
    """
    valid = alpha.dropna()
    if valid.empty:
        return pd.Series(0.0, index=alpha.index)
    weights = np.sign(valid) / len(valid)
    return weights.reindex(alpha.index, fill_value=0.0)
