"""世坤101公式翻译时反复用到的两个小工具，收口一次，不在每个文件里各写一份。

背景（设计文档 §6.5 已经踩过的坑）：pandas/numpy 里 `NaN > 0` 直接算 `False`，不是 `NaN`，
所以任何"用布尔比较模拟三元表达式/直接把布尔值当分数"的公式，warmup 阶段如果不显式拿
原始输入的 `notna()` 重新盖一遍，会冒出"看起来正常但没有意义"的 0/1/-1，而不是老实的 NaN。
"""

from __future__ import annotations

from typing import Union

import pandas as pd

Scalar = Union[int, float]


def _valid_mask(cond: pd.DataFrame, nan_sources: tuple[pd.DataFrame, ...]) -> pd.DataFrame | None:
    if not nan_sources:
        return None
    valid = nan_sources[0].notna()
    for source in nan_sources[1:]:
        valid = valid & source.notna()
    return valid


def ternary(
    cond: pd.DataFrame,
    if_true: Union[pd.DataFrame, Scalar],
    if_false: Union[pd.DataFrame, Scalar],
    *nan_sources: pd.DataFrame,
) -> pd.DataFrame:
    """`cond ? if_true : if_false`，`if_true`/`if_false` 可以是 DataFrame 或标量。

    `nan_sources` 是喂进 `cond` 比较表达式的原始 DataFrame（比如 `cond = a < b` 就传
    `a, b`）——`cond` 本身的比较结果不会带 NaN（pandas 的比较运算把 NaN 参与的比较判成
    False），必须显式用原始输入的缺失情况重新盖一遍，见模块 docstring。
    """
    if not isinstance(if_true, pd.DataFrame):
        if_true = pd.DataFrame(if_true, index=cond.index, columns=cond.columns)
    result = if_true.where(cond, if_false)
    valid = _valid_mask(cond, nan_sources)
    return result if valid is None else result.where(valid)


def bool_to_signal(cond: pd.DataFrame, *nan_sources: pd.DataFrame) -> pd.DataFrame:
    """把布尔条件转成 `{0.0, 1.0}` 的浮点信号，`nan_sources` 缺失的地方结果也是 NaN。

    用于公式直接把一个布尔比较的结果（乘上 -1、或者拿去 rank）当作分数的场景，跟
    `ternary` 是同一个 NaN 处理原则，只是没有 if_true/if_false 两个分支。
    """
    result = cond.astype(float)
    valid = _valid_mask(cond, nan_sources)
    return result if valid is None else result.where(valid)
