"""Regime 相关的批量入口，两块职责：

1. `regime_report()`：把 `BarPanel` 拆包喂给 `sherpa.metrics.regime`，产出跟 `panel.index`
   对齐的状态报告矩阵。拆包这一步不能放进 `sherpa.metrics.regime`——`sherpa.metrics` 包级
   约定是"只依赖 pandas/numpy，不 import 仓库内其他模块"（见 `sherpa/metrics/__init__.py`），
   `sherpa.backtest` 已经依赖 `sherpa.data.schema.BarPanel`（`screening.py`/`alpha_check.py`
   同理），适配层放这里不引入新的依赖方向。

2. `profile_alphas_by_regime()`：批量版条件 IC 画像，对接 `sherpa.metrics.factor.
   conditional_ic_summary()`。它只吃"已经算好的 `ic_series`"，不重新跑
   `alpha.compute()`/`run_alpha_check()`——是跟第一层 `screen_alphas` 产线完全解耦的并行
   旁路诊断，不是它的一部分（`research/REGIME_ALPHA_EVALUATION_WORKFLOW.md` §5.2 微观切片
   诊断），调用方（研究脚本）自己决定 `ic_series` 从哪来、要不要复用已经跑过的 `screen_alphas`
   结果。
"""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from sherpa.data.schema import BarPanel
from sherpa.metrics.factor import conditional_ic_summary
from sherpa.metrics.regime import DEFAULT_LOOKBACK, build_regime_report

DEFAULT_REGIME_DIMENSIONS: tuple[str, ...] = ("trend", "volatility", "dispersion", "liquidity")


def regime_report(
    panel: BarPanel,
    *,
    benchmark_symbol: str = "BTCUSDT",
    ma_period: int = DEFAULT_LOOKBACK,
    vol_window: int = DEFAULT_LOOKBACK,
    lookback: int = DEFAULT_LOOKBACK,
) -> pd.DataFrame:
    """对整条 `panel` 历史做全时序连续的 regime 打标（`REGIME_FRAMEWORK_GUIDE.md` §5.2）。"""
    return build_regime_report(
        panel.close,
        panel.quote_volume,
        panel.taker_buy_quote_volume,
        benchmark_symbol=benchmark_symbol,
        ma_period=ma_period,
        vol_window=vol_window,
        lookback=lookback,
    )


def profile_alphas_by_regime(
    ic_series_by_alpha: Mapping[str, pd.Series],
    regime: pd.DataFrame,
    *,
    dimensions: Sequence[str] = DEFAULT_REGIME_DIMENSIONS,
) -> pd.DataFrame:
    """对 `ic_series_by_alpha` 里每个 alpha，分别在 `regime` 的每个维度上做条件 IC 切片统计，
    汇总成一张长表：列为 `alpha, dimension, state, samples, ic_mean, ic_std, ic_ir, win_rate, t_stat, p_value`
    （`state` 里含每个维度自己的 `"ALL"` 基线行）。

    长表而不是宽表（`REGIME_ALPHA_EVALUATION_WORKFLOW.md` §6 那种"一行一个 alpha、一列一个
    命名状态"的决策矩阵），是因为现在四个维度各自的状态还没有归并/挑选出"哪几个组合值得单独
    成列"——先如实穷举，宽表的列该怎么选，等看过这张长表的实际分布后再决定（跟之前确认过的
    "先穷举、落地体检时再归并"一致）。`regime` 通常直接传 `regime_report()` 的输出。
    """
    rows = []
    for alpha_name, ic_series in ic_series_by_alpha.items():
        for dim in dimensions:
            profile = conditional_ic_summary(ic_series, regime[dim])
            profile = profile.rename_axis("state").reset_index()
            profile.insert(0, "dimension", dim)
            profile.insert(0, "alpha", alpha_name)
            rows.append(profile)
    return pd.concat(rows, ignore_index=True)
