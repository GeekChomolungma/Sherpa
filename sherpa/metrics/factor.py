"""第一层·信息预测力检验（`docs/backtest_principle.md` 一、）：RankIC / IC_IR / 分位数单调性。

只吃两个矩阵：alpha 分数 `(T,N)` DataFrame + 未来收益率 `(T,N)` DataFrame，不做任何截面
预处理（去极值/中性化）——那是调用方（`sherpa.backtest.alpha_check`）的职责。
"""

from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np
import pandas as pd


def rank_ic(alpha: pd.DataFrame, forward_returns: pd.DataFrame) -> pd.Series:
    """逐期 Spearman 秩相关系数（原理文档 §1.2(1)）。

    index 对齐取交集；每一期只用两边都不缺失的 symbol。某一期这样的 symbol 不足 2 个、或某一边
    整行恒定（比如占位因子 / 某个截面全部打平）时相关系数无意义，返回 NaN。

    **实现：所有期一次算完（向量化），不再逐行调用 `corrwith(method="spearman")`。** Spearman =
    对两边分别取秩（并列取平均秩）后的 Pearson 相关，这里用 pandas 按行排名（C 实现）+ numpy 逐行
    协方差一次算完，跟 `corrwith` 的逐行结果在浮点舍入级别内一致
    （`tests/metrics/test_factor_vectorized_equivalence.py` 保留了旧实现做对比）。
    `±inf` 跟旧实现一样当作有效值参与排名（最大 / 最小），只有 NaN 算缺失。
    """
    alpha, forward_returns = alpha.align(forward_returns, join="inner", axis=0)
    common_cols = alpha.columns.intersection(forward_returns.columns)
    a = alpha[common_cols]
    b = forward_returns[common_cols]

    both = a.notna() & b.notna()
    ranks_a = a.where(both).rank(axis=1).to_numpy(dtype="float64")
    ranks_b = b.where(both).rank(axis=1).to_numpy(dtype="float64")
    n = both.sum(axis=1).to_numpy(dtype="float64")

    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)  # 全缺失行的 nanmean
        centered_a = ranks_a - np.nanmean(ranks_a, axis=1, keepdims=True)
        centered_b = ranks_b - np.nanmean(ranks_b, axis=1, keepdims=True)
        cov = np.nansum(centered_a * centered_b, axis=1)
        var_a = np.nansum(centered_a * centered_a, axis=1)
        var_b = np.nansum(centered_b * centered_b, axis=1)
        ic = cov / np.sqrt(var_a * var_b)
    ic[(n < 2) | (var_a == 0) | (var_b == 0)] = np.nan
    return pd.Series(ic, index=a.index, name="rank_ic")


def forward_returns(close: pd.DataFrame, *, horizon: int = 1, delay: int = 0) -> pd.DataFrame:
    """IC 检验用的"未来收益"标签：t 行 = 从 `close[t + delay]` 持有到 `close[t + delay + horizon]` 的收益。

    - `delay`（执行延迟，单位 bar）：信号在 bar t 收盘时算出，但实际要晚 `delay` 根 bar 才能
      按收盘价成交。`delay=0` 是"刚好在信号那根 bar 的收盘价成交"的理想情况；`delay=1` 跳过
      紧接着的那一根 bar，用来检验信号是不是只在"收盘后立刻成交"那一瞬间有效——短周期反转因子
      的 IC 里常混有买卖价差来回跳（bid-ask bounce）的成分，这部分实盘吃不到，延迟一根 bar
      后会大幅消失。
    - `horizon`（持有期，单位 bar）：收益累计几根 bar。`horizon > 1` 时相邻两期的标签有重叠，
      IC 序列会自相关，显著性要看 Newey–West t（`ic_significance` 已处理）。

    `horizon=1, delay=0` 等价于历史写法 `close.pct_change().shift(-1)`；`delay=1` 等价于
    `close.pct_change().shift(-2)`。末尾 `horizon + delay` 行没有未来数据，为 NaN。
    """
    if horizon < 1:
        raise ValueError(f"horizon 至少是 1 根 bar，收到 {horizon}")
    if delay < 0:
        raise ValueError(f"delay 不能为负（那等于用未来信息），收到 {delay}")
    return close.pct_change(periods=horizon, fill_method=None).shift(-(horizon + delay))


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


@dataclass(frozen=True)
class ICSignificance:
    """RankIC 均值是否显著异于 0 的检验结果（Newey–West t 检验）。"""

    t_stat: float
    p_value: float
    samples: int
    lags: int


def newey_west_lags(samples: int) -> int:
    """Newey–West 自动滞后阶数的经验公式 `floor(4 * (n/100)^(2/9))`（Newey & West, 1994）。

    4h bar 全样本 n≈13000 时约 11 阶；某个 regime state 切片 n≈100 时约 4 阶。
    """
    if samples <= 1:
        return 0
    return int(math.floor(4.0 * (samples / 100.0) ** (2.0 / 9.0)))


def ic_significance(ic_series: pd.Series, *, lags: int | None = None) -> ICSignificance:
    """RankIC 均值的 Newey–West（HAC）t 检验：`t = mean / se_NW`，p 为双侧正态近似。

    为什么不用朴素的 `t = IC_IR × sqrt(n)`：因子值逐 bar 变化慢，相邻两期的 IC 往往正相关，
    这时 n 期 IC 并不是 n 个独立样本，朴素 t 会系统性高估显著性。Newey–West 用 Bartlett
    权重把前 `lags` 阶自协方差加进方差估计，自相关越强、标准误越大、t 越小。IC 序列没有
    自相关时，结果退化成朴素 t（只差一个 n 与 n-1 的分母口径）。

    `ic_series` 是按时间排好序的序列（`rank_ic` 的输出、或者它按 regime 取出的子序列）；
    NaN 会被先剔除。对 regime 子序列来说，被剔除掉的其它 state 的 bar 会让"相邻"变成
    "子序列里相邻"，这是一个近似——同一个 state 往往连续出现好多根 bar，近似误差不大。

    p 值用正态分布近似（`erfc(|t| / sqrt(2))`），不引入 scipy：样本数上百时 t 分布和
    正态分布几乎没有差别；样本很少的切片本来就会被 `low_sample` 标记，p 值只作参考。

    边界情况跟 `ic_summary` 同一套口径：样本 < 3 返回 NaN；标准误≈0 且均值明显非零返回
    `±inf` / p=0（每一期 IC 都一样且不为 0，是完美稳定的信号）；均值也≈0 返回 NaN。
    """
    clean = ic_series.dropna()
    n = int(clean.shape[0])
    if n < 3:
        return ICSignificance(t_stat=float("nan"), p_value=float("nan"), samples=n, lags=0)

    if lags is None:
        lags = newey_west_lags(n)
    lags = max(0, min(int(lags), n - 1))

    values = clean.to_numpy(dtype=float)
    mean = float(values.mean())
    x = values - mean
    long_run_var = float(x @ x) / n
    for k in range(1, lags + 1):
        weight = 1.0 - k / (lags + 1.0)
        long_run_var += 2.0 * weight * float(x[k:] @ x[:-k]) / n
    # Bartlett 权重保证理论上 long_run_var >= 0，这里只防浮点舍入出现极小负数。
    long_run_var = max(long_run_var, 0.0)
    se = math.sqrt(long_run_var / n)

    if se > 1e-12:
        t_stat = mean / se
    elif abs(mean) > 1e-9:
        t_stat = float("inf") if mean > 0 else float("-inf")
    else:
        return ICSignificance(t_stat=float("nan"), p_value=float("nan"), samples=n, lags=lags)

    p_value = 0.0 if math.isinf(t_stat) else math.erfc(abs(t_stat) / math.sqrt(2.0))
    return ICSignificance(t_stat=float(t_stat), p_value=float(p_value), samples=n, lags=lags)


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
        significance = ic_significance(values)
        clean = values.dropna()
        return {
            "samples": int(clean.shape[0]),
            "ic_mean": summary.mean,
            "ic_std": summary.std,
            "ic_ir": summary.ic_ir,
            "win_rate": float((clean > 0).mean()) if not clean.empty else float("nan"),
            "t_stat": significance.t_stat,
            "p_value": significance.p_value,
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

    **实现：所有期一次算完（向量化），不再逐期 `qcut` + `groupby`。** 分组规则与旧实现逐期
    `pd.qcut(降序名次, n_quantiles)` 完全一致：每期有效 symbol 按 alpha 降序排名（并列按列顺序，
    即 `method="first"`），名次 1..n 按等分位切成 q 组——名次 r 落在第 `ceil(q·(r−1)/(n−1))` 组
    （r=1 归第 1 组）。这就是 `qcut` 在 1..n 上用线性插值算分位点、右闭区间分箱的结果，只是写成了
    一个公式，所有期同时算。
    """
    alpha, forward_returns = alpha.align(forward_returns, join="inner", axis=0)
    common_cols = alpha.columns.intersection(forward_returns.columns)
    a = alpha[common_cols]
    r = forward_returns[common_cols]
    labels = list(range(1, n_quantiles + 1))

    valid = a.notna() & r.notna()
    n = valid.sum(axis=1).to_numpy(dtype="float64")[:, None]  # (T, 1)
    # rank 降序：alpha 最高的 symbol 拿到名次 1，一定落进第 1 组，跟"组1=多头最高分"的约定对齐。
    desc_rank = a.where(valid).rank(axis=1, method="first", ascending=False).to_numpy(dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        bucket = np.ceil(n_quantiles * (desc_rank - 1) / (n - 1))
    bucket = np.where(n > 1, np.maximum(bucket, 1), 1)  # 名次 1（以及只有 1 个 symbol 时）归第 1 组
    returns = r.to_numpy(dtype="float64")
    is_valid = valid.to_numpy()

    means = np.full((len(a.index), n_quantiles), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        for k in labels:
            in_group = is_valid & (bucket == k)
            members = in_group.sum(axis=1)
            total = np.where(in_group, returns, 0.0).sum(axis=1)
            means[:, k - 1] = np.where(members > 0, total / np.maximum(members, 1), np.nan)
    means[n[:, 0] < n_quantiles] = np.nan
    return pd.DataFrame(means, index=a.index, columns=labels).sort_index()


def is_monotonic_decreasing(mean_quantile_returns: pd.Series) -> bool:
    """分位数单调性检验（原理文档 §1.2(3)）：组1(多头)到组K(空头)的均值是否逐组非递增。

    用 pandas 内置的非严格单调判断（允许相邻两组相等），而不是数学上的"严格递减"——真实
    数据里出现两组均值完全相等的概率极低，严格递减在浮点误差下反而容易误判失败。
    """
    clean = mean_quantile_returns.dropna()
    if len(clean) < 2:
        return False
    return bool(clean.is_monotonic_decreasing)
