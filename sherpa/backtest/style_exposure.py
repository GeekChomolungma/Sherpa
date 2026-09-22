"""BarPanel 适配层：把 `sherpa.risk` 的纯 pandas 中性化函数接上 `BarPanel`。

跟 `sherpa.backtest.regime_screening.regime_report()` 对 `sherpa.metrics.regime` 的处理
方式一致——`sherpa.risk` 包级约定是"只依赖 pandas/numpy，不 import 仓库内其他模块"（见
`sherpa/risk/__init__.py`），`BarPanel` 拆包这一步放在这里，不污染 `sherpa.risk` 本身。
"""

from __future__ import annotations

import pandas as pd

from sherpa.alpha.ops import log
from sherpa.data.schema import BarPanel
from sherpa.risk.exposure import DEFAULT_BETA_WINDOW, rolling_beta

DEFAULT_BENCHMARK_SYMBOL = "BTCUSDT"


def default_style_exposures(
    panel: BarPanel,
    *,
    benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
    beta_window: int = DEFAULT_BETA_WINDOW,
) -> dict[str, pd.DataFrame]:
    """阶段一中性化的标准暴露集合：Beta（逐 symbol 滚动对 `benchmark_symbol`） + Size
    （`quote_volume` 的 `log` 变换——原始成交额右尾极重，直接拿去回归会被少数极端值主导，
    跟 Barra 风险模型用 log 市值做 Size 因子是同一个考虑）。

    `quote_volume` 里恰好等于 0 的格子（真实存在，不是缺失——某些 symbol 某一期确实没有
    成交但仍在上市）先掩成 `NaN` 再取 `log`：`log(0) = -inf`，直接喂给
    `sherpa.risk.neutralize.neutralize()` 的截面 OLS 会在 LAPACK 层直接报错崩溃，而
    `-inf` 本身也没有"更负的成交额"这种经济含义——这一期这个 symbol 应该被当成缺失，
    不该硬造一个发散值。负数理论上不该出现（成交额不可能为负），一并同口径处理防御性更好。

    直接喂给 [`sherpa.risk.neutralize.neutralize`](../risk/neutralize.py) 当 `exposures`
    用，也是 `sherpa.backtest.screening.screen_alphas(..., exposures=...)` 的标准用法。
    """
    return {
        "beta": rolling_beta(panel.close, benchmark_symbol=benchmark_symbol, window=beta_window),
        "size": log(panel.quote_volume.where(panel.quote_volume > 0)),
    }
