"""第一层·信息预测力检验（`docs/backtest_principle.md` 一、）：RankIC / IC_IR / 分位数单调性。

只吃两个矩阵：alpha 分数 `(T,N)` DataFrame + 未来收益率 `(T,N)` DataFrame，不做任何截面
预处理（去极值/中性化）——那是调用方（`sherpa.backtest.alpha_check`）的职责。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass

import pandas as pd


def rank_ic(alpha: pd.DataFrame, forward_returns: pd.DataFrame) -> pd.Series:
    """逐期 Spearman 秩相关系数（原理文档 §1.2(1)）。

    index 对齐取交集；某一期非缺失的 symbol 数不足 2 个、或某一整行恒定（比如占位因子/
    某个截面全部打平）时相关系数无意义，返回 NaN（`DataFrame.corrwith` 对这些情况的默认
    行为已经是 NaN，不需要额外处理）。scipy 在恒定输入时会顺带打一条 `ConstantInputWarning`
    到 stderr——这条警告描述的正是我们已经处理好、预期之内的 NaN 情况，不是需要调用方
    关注的异常，批量跑几十上百个因子时会刷屏，这里显式吞掉。
    """
    alpha, forward_returns = alpha.align(forward_returns, join="inner", axis=0)
    common_cols = alpha.columns.intersection(forward_returns.columns)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ic = alpha[common_cols].corrwith(forward_returns[common_cols], axis=1, method="spearman")
    return ic.rename("rank_ic")


@dataclass(frozen=True)
class ICSummary:
    """RankIC 序列的统计分布特征（原理文档 §1.2(2)）。"""

    mean: float
    std: float
    ic_ir: float


def ic_summary(ic_series: pd.Series) -> ICSummary:
    """Mean(RankIC) 和 IC_IR = Mean/Std。标准差为 0 或样本为空时 IC_IR 定义为 NaN。"""
    clean = ic_series.dropna()
    if clean.empty:
        return ICSummary(mean=float("nan"), std=float("nan"), ic_ir=float("nan"))
    mean = float(clean.mean())
    std = float(clean.std())
    # 用绝对容差而不是 `!= 0`：RankIC 取值范围是 [-1,1]，浮点运算的舍入误差可能让理论上
    # 完全相等的一组值算出 std ~= 1e-17 而不是精确的 0，直接除会得到没有意义的巨大 IC_IR。
    if std > 1e-9:
        ic_ir = float(mean / std)
    elif abs(mean) > 1e-9:
        # std~=0 且 mean 明显非零：每一期 RankIC 都几乎相同、且不是"几乎都是0"，这是
        # "极端稳定的强信号"（比如测试用的理想合成因子），比值的数学极限是 ±inf，不是 NaN
        # ——如果这里返回 NaN，反而会让"完美因子"被 §8.4.1 的 IC_IR 阈值判定判成不通过。
        ic_ir = float("inf") if mean > 0 else float("-inf")
    else:
        # std~=0 且 mean~=0：真正的 0/0，没有任何信息，NaN 才是诚实的表达。
        ic_ir = float("nan")
    return ICSummary(mean=mean, std=std, ic_ir=ic_ir)


def conditional_ic_summary(ic_series: pd.Series, regime: pd.Series) -> pd.DataFrame:
    """按 `regime` 的取值对 `ic_series` 做条件切片统计（原理参考 `research/
    REGIME_ALPHA_EVALUATION_WORKFLOW.md` §5 步骤4），返回一行一个类别的画像表，行索引里
    多一个 `"ALL"` 基线行。

    `regime` 可以是单个维度的状态列（比如 `regime_report["trend"]`，值是 "bull"/"bear"/
    "neutral"），也可以是组合结论列（`regime_report["regime_label"]`）——本函数不关心
    label 是怎么来的，只按值分组统计,所以同一份实现可以喂两种粒度的画像需求。

    跟 `regime` 对齐后，`regime` 为 `NA` 的行（比如打标函数自己的滚动窗口 warm-up 期）会被
    整行剔除，既不进 `"ALL"` 基线也不进任何分组——`"ALL"` 的样本量因此正好等于各分组样本量
    之和，两者可以直接比较增量信息，不会因为 `"ALL"` 悄悄多算了一段分组阶段完全没覆盖到的
    历史而失真。这里特意跟 `REGIME_ALPHA_EVALUATION_WORKFLOW.md` 给的参考代码不一样（那份
    示例用未过滤的完整 `ic_series` 当基线）——两种口径都不算错，这里选了口径更严格的一种。
    """
    ic_series, regime = ic_series.align(regime, join="inner")
    known = regime.notna()
    ic_series = ic_series[known]
    regime = regime[known]

    def _row(values: pd.Series) -> dict[str, float]:
        summary = ic_summary(values)
        clean = values.dropna()
        return {
            "samples": int(clean.shape[0]),
            "ic_mean": summary.mean,
            "ic_std": summary.std,
            "ic_ir": summary.ic_ir,
            "win_rate": float((clean > 0).mean()) if not clean.empty else float("nan"),
        }

    rows: dict[str, dict[str, float]] = {"ALL": _row(ic_series)}
    for label, group in ic_series.groupby(regime):
        rows[str(label)] = _row(group)

    return pd.DataFrame.from_dict(rows, orient="index")


def quantile_returns(alpha: pd.DataFrame, forward_returns: pd.DataFrame, n_quantiles: int = 10) -> pd.DataFrame:
    """逐期按 alpha 分数分 `n_quantiles` 组的未来收益均值（原理文档 §1.2(3)）。

    列标签 1..n_quantiles，**1 = 当期 alpha 最高的一组（多头），n_quantiles = 最低的一组
    （空头）**——跟原理文档"第1组（多头最高分）到第K组（空头最低分）"的表述保持一致。
    某一期非缺失 symbol 数不足 `n_quantiles` 个时该期整行为 NaN（分不出这么多组）。
    """
    alpha, forward_returns = alpha.align(forward_returns, join="inner", axis=0)
    common_cols = alpha.columns.intersection(forward_returns.columns)
    a = alpha[common_cols]
    r = forward_returns[common_cols]
    labels = list(range(1, n_quantiles + 1))

    rows: dict = {}
    for t in a.index:
        a_row = a.loc[t]
        r_row = r.loc[t]
        mask = a_row.notna() & r_row.notna()
        if int(mask.sum()) < n_quantiles:
            rows[t] = pd.Series(float("nan"), index=labels)
            continue
        # rank 降序：alpha 最高的 symbol 拿到 rank 1，qcut 按升序 rank 分箱，
        # 所以 rank 1 一定落进第一个箱 -> label 1，跟"组1=多头最高分"的约定对齐。
        desc_rank = a_row[mask].rank(method="first", ascending=False)
        bucket = pd.qcut(desc_rank, n_quantiles, labels=False) + 1
        rows[t] = r_row[mask].groupby(bucket).mean().reindex(labels)

    return pd.DataFrame.from_dict(rows, orient="index").reindex(columns=labels).sort_index()


def is_monotonic_decreasing(mean_quantile_returns: pd.Series) -> bool:
    """分位数单调性检验（原理文档 §1.2(3)）：组1(多头)到组K(空头)的均值是否逐组非递增。

    用 pandas 内置的非严格单调判断（允许相邻两组相等），而不是数学上的"严格递减"——真实
    数据里出现两组均值完全相等的概率极低，严格递减在浮点误差下反而容易误判失败。
    """
    clean = mean_quantile_returns.dropna()
    if len(clean) < 2:
        return False
    return bool(clean.is_monotonic_decreasing)
