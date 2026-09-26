"""关卡2 合成用的纯函数：截面标准化、方向估计、等权合成、按 regime 路由合成、分段切分、评估指标。

只依赖 pandas 和 `sherpa.metrics.factor`，不碰 IO、不读 research 配置——`README.md` §8：合成逻辑
将来要原样搬进 `sherpa`，给回测和实盘共用（离线 / 在线信号必须逐笔一致），所以从一开始就写成
"输入矩阵、输出矩阵"的纯函数。

矩阵约定跟 sherpa 其余部分一致：`(T, N)` DataFrame，行 = bar 时间，列 = symbol。
"""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from sherpa.metrics.factor import ic_significance, ic_summary, rank_ic


# ---------------------------------------------------------------------------
# 合成前的预处理
# ---------------------------------------------------------------------------

def cross_sectional_rank(scores: pd.DataFrame) -> pd.DataFrame:
    """逐期截面百分位排名，平移到 [-0.5, 0.5]（截面中位数约为 0）。NaN 保持 NaN。

    为什么合成前必须先做这一步：不同因子的原始分数量级、分布差别极大（有的是秩，有的是价格比率），
    直接相加等于让量级最大的那个因子独占权重。换成截面排名后，每个因子在每一期都落在同一个尺度上，
    "等权"才名副其实。用排名而不是 z-score，是为了不让少数极端值主导。
    """
    return scores.rank(axis=1, pct=True) - 0.5


def ic_sign(ic_series: pd.Series, min_samples: int = 30) -> float:
    """IC 均值的符号：+1（分数越高、未来收益越高）/ -1（反向使用）/ 0（样本不足或均值恰为 0，不参与合成）。"""
    clean = ic_series.dropna()
    if len(clean) < min_samples:
        return 0.0
    mean = float(clean.mean())
    if mean > 0:
        return 1.0
    if mean < 0:
        return -1.0
    return 0.0


def estimate_signs(
    ic_by_factor: Mapping[str, pd.Series],
    selection_mask: pd.Series,
    *,
    min_samples: int = 30,
) -> dict[str, float]:
    """每个因子在**选择段**上的全局方向。只用 `selection_mask` 为 True 的 bar，验证段的 IC 一律不看。"""
    return {name: ic_sign(ic[selection_mask.reindex(ic.index, fill_value=False)], min_samples) for name, ic in ic_by_factor.items()}


def estimate_state_signs(
    ic_by_factor: Mapping[str, pd.Series],
    selection_mask: pd.Series,
    regime_column: pd.Series,
    state_factors: Mapping[str, Sequence[str]],
    global_signs: Mapping[str, float],
    *,
    min_samples: int = 100,
) -> dict[str, dict[str, float]]:
    """每个 state 下各候选因子的方向：在选择段里、属于该 state 的 bar 上估计。

    同一个因子在不同 state 下方向可能相反（比如某个量价因子在趋势市里是动量、在震荡市里是反转），
    所以路由合成要按 state 取方向。该 state 样本不足 `min_samples` 时退回全局方向——小样本 state
    的 IC 均值符号本身就不可靠。
    """
    signs: dict[str, dict[str, float]] = {}
    for state, factors in state_factors.items():
        in_state = selection_mask & (regime_column == state).fillna(False)
        signs[state] = {}
        for name in factors:
            ic = ic_by_factor[name]
            sign = ic_sign(ic[in_state.reindex(ic.index, fill_value=False)], min_samples)
            signs[state][name] = sign if sign != 0.0 else global_signs.get(name, 0.0)
    return signs


# ---------------------------------------------------------------------------
# 合成
# ---------------------------------------------------------------------------

def equal_weight_composite(
    ranked: Mapping[str, pd.DataFrame],
    signs: Mapping[str, float],
    factors: Sequence[str],
) -> pd.DataFrame:
    """等权合成：`mean_i( sign_i × rank_i )`，逐 (bar, symbol) 只平均当期有值的因子。

    某个 symbol 在某一期缺了部分因子（比如刚上线、窗口还没攒够），就用它有值的那几个因子平均，
    而不是整格丢掉；一个因子都没有才是 NaN。方向为 0 的因子（样本不足、方向不明）不参与。
    """
    used = [name for name in factors if signs.get(name, 0.0) != 0.0]
    if not used:
        raise ValueError(f"没有可用于合成的因子（候选 {list(factors)} 的方向全部为 0）")
    total = None
    count = None
    for name in used:
        signed = ranked[name] * signs[name]
        total = signed.fillna(0.0) if total is None else total.add(signed.fillna(0.0), fill_value=0.0)
        present = signed.notna().astype(float)
        count = present if count is None else count.add(present, fill_value=0.0)
    return total.where(count > 0) / count.where(count > 0)


def routed_composite(
    ranked: Mapping[str, pd.DataFrame],
    state_signs: Mapping[str, Mapping[str, float]],
    state_factors: Mapping[str, Sequence[str]],
    regime_column: pd.Series,
    fallback: pd.DataFrame,
) -> pd.DataFrame:
    """按 regime 路由的等权合成：每根 bar 用它当时所处 state 的因子名单（和该 state 的方向）等权合成。

    `regime_column` 必须是 point-in-time 的标签（`regime_report()` 用滚动分位数，只看 <= t 的数据），
    否则就是用未来信息选因子。以下情况这根 bar 退回 `fallback`（通常是不分 regime 的 L0 合成分数）：
    - regime 标签为 NA（滚动窗口 warm-up 期）；
    - 当前 state 的名单为空，或名单里的因子方向全部为 0。
    """
    result = fallback.copy()
    for state, factors in state_factors.items():
        signs = state_signs.get(state, {})
        if not any(signs.get(name, 0.0) != 0.0 for name in factors):
            continue
        rows = (regime_column == state).fillna(False).reindex(result.index, fill_value=False)
        if not rows.any():
            continue
        composite = equal_weight_composite(ranked, signs, factors)
        result.loc[rows] = composite.loc[rows]
    return result


# ---------------------------------------------------------------------------
# 分段与评估
# ---------------------------------------------------------------------------

def segment_masks(index: pd.DatetimeIndex, validation_start: pd.Timestamp, purge_bars: int) -> tuple[pd.Series, pd.Series]:
    """把研究段切成 (选择段, 验证段) 两个布尔掩码。

    选择段末尾去掉 `purge_bars` 根 bar：t 时刻的标签要用到 `close[t + delay + horizon]`，选择段最后几根
    bar 的标签会伸进验证段。用它们估计方向，等于偷看了验证段的价格，所以要删掉（purge）。
    `purge_bars` 通常取 `horizon_bars + execution_delay_bars`。
    """
    in_validation = pd.Series(index >= validation_start, index=index)
    before = pd.Series(index < validation_start, index=index)
    boundary = int(before.sum())
    selection = before.copy()
    if purge_bars > 0 and boundary > 0:
        selection.iloc[max(0, boundary - purge_bars):boundary] = False
    return selection, in_validation


def summarize_ic(ic_series: pd.Series) -> dict[str, float]:
    """一条 IC 序列的全部统计口径（跟阶段一 profile 的列一致），用于方案对比表。"""
    clean = ic_series.dropna()
    summary = ic_summary(ic_series)
    significance = ic_significance(ic_series)
    return {
        "samples": int(clean.shape[0]),
        "ic_mean": summary.mean,
        "ic_std": summary.std,
        "ic_ir": summary.ic_ir,
        "t_stat": significance.t_stat,
        "p_value": significance.p_value,
        "win_rate": float((clean > 0).mean()) if not clean.empty else float("nan"),
    }


def score_autocorr(scores: pd.DataFrame) -> pd.Series:
    """相邻两期分数的截面 Spearman 相关（逐 bar）：越接近 1，排序越稳定、换手越低。

    这是关卡3（摩擦测试）之前的早期预警：两个方案 IC 差不多时，分数更稳定的那个扣完成本通常更好。
    """
    return rank_ic(scores, scores.shift(1)).rename("score_autocorr")
