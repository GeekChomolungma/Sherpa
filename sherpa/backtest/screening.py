"""批量因子筛选报告（设计文档 §8.4.1 的批量版）：一次性把 `AlphaEngine` 里所有 alpha 都跑
一遍第一层 `alpha_check`，汇总成一张按 IC_IR 排序的排行榜。

不复用 `AlphaEngine.compute_history()`——那是一个 dict comprehension，只要其中一个 alpha
`raise`（比如世坤101里 19 个占位因子），整批直接失败，拿不到任何结果。批量筛选场景恰恰
经常需要在"还没确认哪些因子能算"的阶段就跑一遍全集，所以这里逐个 alpha 单独调用、单独
捕获 `NotImplementedError`，不让一个占位因子拖累其余因子的结果。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

import pandas as pd

from sherpa.alpha.engine import AlphaEngine
from sherpa.data.schema import BarPanel
from sherpa.risk.neutralize import neutralize

from .alpha_check import run_alpha_check


@dataclass(frozen=True)
class ScreeningReport:
    """`screen_alphas()` 的结果：能算的因子进 `table`，算不出来的因子进 `errors`。"""

    table: pd.DataFrame  # index=qualified_name，columns=[ic_mean, ic_std, ic_ir, passed]
    errors: dict[str, str] = field(default_factory=dict)  # qualified_name -> 报错信息


def screen_alphas(
    alpha_engine: AlphaEngine,
    panel: BarPanel,
    forward_returns: pd.DataFrame,
    *,
    n_quantiles: int = 10,
    ic_ir_threshold: float = 0.5,
    exposures: Mapping[str, pd.DataFrame] | None = None,
) -> ScreeningReport:
    """对 `alpha_engine` 里每个 alpha 跑一遍 `run_alpha_check`，汇总成一张按 IC_IR 从高到低
    排序的表。`forward_returns` 的口径跟 `run_alpha_check` 一致（要跟 alpha 对齐"未来"收益率，
    调用方自己按需要的预测周期构造，比如 `panel.close.pct_change().shift(-1)`）。

    `exposures` 非 None 时，每个因子的原始分数在喂给 `run_alpha_check` 之前先用
    `sherpa.risk.neutralize.neutralize()` 对这些暴露矩阵（比如 Beta/Size）做逐期截面 OLS
    残差化，再拿残差分数去算 IC——`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2，剔除因子
    原始表现里"被动骑风险暴露"的那部分。默认 `None`（关闭）保持向后兼容；调用方通常传
    `sherpa.backtest.style_exposure.default_style_exposures(panel)`。

    只吞掉 `NotImplementedError`（世坤101里那批因缺字段占位不实现的因子会抛这个）——除此
    之外的异常照常往外抛，不能把真正的 bug 也悄悄吞掉、伪装成"这个因子算不出来"。
    """
    rows: dict[str, dict[str, float | bool]] = {}
    errors: dict[str, str] = {}

    for alpha in alpha_engine.alphas:
        try:
            history = alpha.compute(panel)
        except NotImplementedError as exc:
            errors[alpha.qualified_name] = str(exc)
            continue

        if exposures is not None:
            history = neutralize(history, exposures)

        result = run_alpha_check(
            history, forward_returns, n_quantiles=n_quantiles, ic_ir_threshold=ic_ir_threshold
        )
        rows[alpha.qualified_name] = {
            "ic_mean": result.ic_mean,
            "ic_std": result.ic_std,
            "ic_ir": result.ic_ir,
            "passed": result.passed,
        }

    table = pd.DataFrame.from_dict(rows, orient="index", columns=["ic_mean", "ic_std", "ic_ir", "passed"])
    if not table.empty:
        table = table.sort_values("ic_ir", ascending=False, na_position="last")
    return ScreeningReport(table=table, errors=errors)
