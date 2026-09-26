"""截面中性化：把因子原始分数对风格/风险暴露做逐期截面 OLS，取残差作为纯净 alpha。

逐个时间戳单独回归，不是把整个 `(T, N)` 面板拉平成一个大数据集做一次全局 OLS——因子分数
对 Beta/Size 的敏感程度不假设是常数，每个截面自己拟合出一套系数，呼应 Barra 风险模型的标准
做法：暴露的经济含义是"在这一个时间点的横截面上，这个因子有多少信息量能被系统性风险解释
掉"，不是"整个历史上平均解释了多少"——后者会把不同 regime 下截然不同的暴露强度抹平成一条
虚假的常数直线。

跟 `sherpa.metrics`/`sherpa.risk.exposure` 同一条包级约定：只依赖 pandas/numpy，不 import
仓库内其他模块，也不认识 `sherpa.alpha.Alpha`——中性化是一个作用于"任意因子原始分数矩阵"的
通用变换，不关心这个矩阵到底是哪个具体因子算出来的。
"""

from __future__ import annotations

from typing import Mapping

import numpy as np
import pandas as pd


# 按时间分块做批量回归，控制中间数组 (rows, N, K) 的内存。
_ROW_CHUNK = 2000


def neutralize(raw_score: pd.DataFrame, exposures: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """逐期截面 OLS 残差化：`raw_score(t) ~ 截距 + sum(exposures[name](t))`，返回残差矩阵。

    `exposures` 里每个矩阵按 `raw_score` 的 index/columns 对齐（比如
    `sherpa.risk.exposure.rolling_beta()` 的输出、或者 `ops.log(panel.quote_volume)`
    这样的 Size 代理；对不上的位置当缺失处理）。某一期某个 symbol 只要在 `raw_score` 或任一
    `exposures` 里缺失，这一期这个 symbol 就被排除在那一期的回归之外，不强行填充。`+inf`/`-inf`
    （比如 Size 代理算 `log(0)`）跟 `NaN` 同等对待，一起被排除。

    某一期有效样本数不够（`< len(exposures) + 2`，即至少要能同时估出截距、每个暴露的
    系数、还剩至少 1 个自由度算残差）时，这一期整行残差为 NaN——回归本身没有统计意义时，
    诚实地不产出一个看似正常实则没有支撑的数字。某一期求解失败（`LinAlgError`）也当作这一期
    算不出来，跳过而不是让整个批量任务崩掉。

    **实现：一次解完所有期的回归（向量化），不再逐期循环。** 每一期都是同一个形式的小回归
    （K 个暴露 + 截距），逐期用 pandas 拼表再调 `lstsq` 时，时间几乎全花在每一轮的 Python/pandas
    开销上。这里把所有期堆成 (T, N, K) 的数组：
    1. 用有效掩码把缺失位置排除在外，逐期算截面均值，把分数和暴露都**逐期去均值**——等价于回归里
       带截距，而且让方程组的条件数更好（Size 代理的量级在 10 左右，不去均值会放大浮点误差）；
    2. 逐期组出 K×K 的正规方程 `X'X β = X'y`，用批量伪逆一次解完所有期。伪逆也能处理某一期暴露
       在截面上恰好是常数（去均值后整列为 0、共线）的情况，结果等于把这一列去掉后的最小二乘，
       跟 `lstsq` 的最小范数解一致；
    3. 残差 = 去均值后的分数 − 去均值后的暴露 × β。

    跟逐期 `lstsq`（SVD）是两种求解算法，结果在 1e-10 量级内一致，不是逐位相同
    （`tests/risk/test_neutralize_vectorized_equivalence.py` 保留了旧实现做逐元素对比）。
    """
    if not exposures:
        raise ValueError("neutralize() 至少需要一个风险暴露矩阵，不然残差就是原始分数本身，没有意义")

    exposure_names = list(exposures.keys())
    min_valid = len(exposure_names) + 2

    y_all = raw_score.to_numpy(dtype="float64")
    x_all = np.stack(
        [
            exposures[name].reindex(index=raw_score.index, columns=raw_score.columns).to_numpy(dtype="float64")
            for name in exposure_names
        ],
        axis=-1,
    )  # (T, N, K)

    out = np.full(y_all.shape, np.nan)
    for start in range(0, y_all.shape[0], _ROW_CHUNK):
        rows = slice(start, start + _ROW_CHUNK)
        out[rows] = _residualize_block(y_all[rows], x_all[rows], min_valid)
    return pd.DataFrame(out, index=raw_score.index, columns=raw_score.columns)


def _residualize_block(y: np.ndarray, x: np.ndarray, min_valid: int) -> np.ndarray:
    """一块 (rows, N) 分数 + (rows, N, K) 暴露 -> (rows, N) 残差，逐行独立回归。"""
    valid = np.isfinite(y) & np.isfinite(x).all(axis=-1)  # (rows, N)
    counts = valid.sum(axis=1)  # (rows,)
    safe_counts = np.maximum(counts, 1)[:, None]

    y0 = np.where(valid, y, 0.0)
    x0 = np.where(valid[..., None], x, 0.0)
    y_mean = y0.sum(axis=1, keepdims=True) / safe_counts  # (rows, 1)
    x_mean = x0.sum(axis=1, keepdims=True) / safe_counts[..., None]  # (rows, 1, K)
    yc = np.where(valid, y0 - y_mean, 0.0)
    xc = np.where(valid[..., None], x0 - x_mean, 0.0)

    xtx = np.einsum("tnk,tnl->tkl", xc, xc)
    xty = np.einsum("tnk,tn->tk", xc, yc)
    beta = _batched_solve(xtx, xty)  # (rows, K)，失败的行为 NaN

    residual = yc - np.einsum("tnk,tk->tn", xc, beta)

    # 某一期的有效分数在截面上完全相同（因子这一期没有任何排序信息）：正确的残差就是精确的 0，
    # 下游 rank_ic 会据此判定"截面恒定"给 NaN。不能指望浮点运算自己算出 0——若干个相同的浮点数
    # 求平均不一定能精确还原原值，会留下 1e-16 量级的舍入噪声；对噪声排名算出的 IC 是纯随机数，
    # 却会被当成有效样本（旧的逐期 lstsq 实现就是这样，曾让恒为常数的 alpha042 产出了"有效" IC）。
    y_max = np.where(valid, y0, -np.inf).max(axis=1)
    y_min = np.where(valid, y0, np.inf).min(axis=1)
    constant_rows = (counts > 0) & (y_max == y_min)
    residual[constant_rows] = 0.0

    ok_rows = (counts >= min_valid) & np.isfinite(beta).all(axis=1)
    return np.where(valid & ok_rows[:, None], residual, np.nan)


def _batched_solve(xtx: np.ndarray, xty: np.ndarray) -> np.ndarray:
    """批量解 `xtx β = xty`（伪逆，能处理共线）。整批失败时退回逐行，逐行失败的那一期给 NaN。"""
    try:
        return np.einsum("tkl,tl->tk", np.linalg.pinv(xtx, hermitian=True), xty)
    except np.linalg.LinAlgError:
        beta = np.full(xty.shape, np.nan)
        for i in range(xtx.shape[0]):
            try:
                beta[i] = np.linalg.pinv(xtx[i], hermitian=True) @ xty[i]
            except np.linalg.LinAlgError:
                continue
        return beta
