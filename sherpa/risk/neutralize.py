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


def neutralize(raw_score: pd.DataFrame, exposures: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
    """逐期截面 OLS 残差化：`raw_score(t) ~ 截距 + sum(exposures[name](t))`，返回残差矩阵。

    `exposures` 里每个矩阵的 index/columns 都应该跟 `raw_score` 能对齐（比如
    `sherpa.risk.exposure.rolling_beta()` 的输出、或者 `ops.log(panel.quote_volume)`
    这样的 Size 代理）。某一期某个 symbol 只要在 `raw_score` 或任一 `exposures` 里缺失，
    这一期这个 symbol 就被排除在那一期的回归之外，不强行填充。`+inf`/`-inf`（比如
    Size 代理算 `log(0)`）跟 `NaN` 同等对待，一起被排除——不做这一步的话，一个 `-inf`
    混进 `design` 矩阵会让 `numpy.linalg.lstsq` 在 LAPACK 层直接报错崩溃，而不是诚实地
    把这个 symbol 当缺失处理。

    某一期有效样本数不够（`< len(exposures) + 2`，即至少要能同时估出截距、每个暴露的
    系数、还剩至少 1 个自由度算残差）时，这一期整行残差为 NaN——回归本身没有统计意义时，
    诚实地不产出一个看似正常实则没有支撑的数字，而不是硬算一个不可信的残差。同理，如果
    清理过 `inf`/`NaN` 之后这一期的设计矩阵仍然病态到 SVD 无法收敛（`LinAlgError`，极端
    共线或数值尺度问题），也当作这一期算不出来，跳过而不是让整个批量任务崩掉。
    """
    if not exposures:
        raise ValueError("neutralize() 至少需要一个风险暴露矩阵，不然残差就是原始分数本身，没有意义")

    exposure_names = list(exposures.keys())
    min_valid = len(exposure_names) + 2

    residual = pd.DataFrame(float("nan"), index=raw_score.index, columns=raw_score.columns)
    for t in raw_score.index:
        # "__score__" 是内部占位列名，不会跟调用方传入的 exposure 名字（比如 "beta"/"size"）
        # 冲突，避免 pd.DataFrame(dict) 因为重名列互相覆盖。
        columns = {"__score__": raw_score.loc[t]}
        for name in exposure_names:
            columns[name] = exposures[name].loc[t]
        frame = pd.DataFrame(columns).replace([np.inf, -np.inf], np.nan).dropna()

        if len(frame) < min_valid:
            continue

        design = np.column_stack(
            [np.ones(len(frame))] + [frame[name].to_numpy() for name in exposure_names]
        )
        target = frame["__score__"].to_numpy()
        try:
            coefficients, *_ = np.linalg.lstsq(design, target, rcond=None)
        except np.linalg.LinAlgError:
            continue
        fitted = design @ coefficients
        residual.loc[t, frame.index] = target - fitted

    return residual
