"""五个分类文件夹共用的第二步跑法，不是 `sherpa` 库代码——这是研究项目自己的编排脚本。

每个分类文件夹（`industry/`/`price_volume/`/...）下的 `run_vectorized.py` 只是一个几行的
薄封装：import 对应分类的 alpha 列表，调这里的 `run_category()`。这么拆是为了避免 5 份
几乎一样的"逐 alpha 跑 alpha_check 过滤 + run_vectorized_backtest"循环代码。

每个因子的原始分数在跑第一层检验、跑第二层向量化回测之前，都会先经过中性化残差化
（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2，剔除对 Beta/Size 的被动暴露）——不再是可选
开关：这里产出的 Sharpe/IC_IR 如果还是用未剥离的原始分数算，很可能只是在给"骑 Beta"的
因子颁奖，不是真的选币能力，不该继续作为默认行为存在。
"""

from __future__ import annotations

from typing import Callable, Sequence

import pandas as pd

from sherpa.alpha.base import Alpha
from sherpa.backtest.alpha_check import run_alpha_check
from sherpa.backtest.cost_model import CostModel, FixedFeeCostModel
from sherpa.backtest.result import BacktestResult
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.backtest.vectorized import run_vectorized_backtest
from sherpa.data.schema import BarPanel
from sherpa.portfolio.weighting import demean_l1
from sherpa.risk.neutralize import neutralize

from data import label_forward_returns, load_universe_panel

DEFAULT_IC_IR_THRESHOLD = 0.15
DEFAULT_N_QUANTILES = 5


def run_category(
    alpha_classes: Sequence[type[Alpha]],
    *,
    label: str,
    panel: BarPanel | None = None,
    ic_ir_threshold: float = DEFAULT_IC_IR_THRESHOLD,
    n_quantiles: int = DEFAULT_N_QUANTILES,
    weighting_fn: Callable[[pd.Series], pd.Series] = demean_l1,
    cost_model: CostModel | None = None,
) -> dict[str, BacktestResult]:
    """对 `alpha_classes` 里每个 alpha：先中性化残差化，再跑第一层 `alpha_check` 过滤，通过
    的才拿残差分数跑第二层 `run_vectorized_backtest`。占位因子（`compute()` 直接
    `raise NotImplementedError`）如实打印"跳过"，不是 bug——世坤101里 19 个因子本来就因为
    缺行业分类/市值数据算不出来。

    返回值只包含真正跑完第二层的 alpha（`qualified_name -> BacktestResult`），方便调用方
    （比如以后想加一个"跨分类汇总"脚本）继续处理，不用重新解析打印出来的文字。
    """
    cost_model = cost_model or FixedFeeCostModel(fee_bps=5)
    panel = panel if panel is not None else load_universe_panel()
    forward_returns = label_forward_returns(panel)
    exposures = default_style_exposures(panel)

    print(f"== {label}：{len(alpha_classes)} 个因子 ==")
    results: dict[str, BacktestResult] = {}

    for cls in alpha_classes:
        alpha = cls()
        try:
            history = alpha.compute(panel)
        except NotImplementedError as exc:
            print(f"  {alpha.qualified_name}: 跳过（{exc}）")
            continue

        history = neutralize(history, exposures)

        check = run_alpha_check(history, forward_returns, n_quantiles=n_quantiles, ic_ir_threshold=ic_ir_threshold)
        if not check.passed:
            print(f"  {alpha.qualified_name}: 第一层未通过（ic_mean={check.ic_mean:.3f}, "
                  f"ic_ir={check.ic_ir:.3f}），跳过第二层")
            continue

        result = run_vectorized_backtest(history, panel, weighting_fn, cost_model)
        results[alpha.qualified_name] = result
        print(
            f"  {alpha.qualified_name}: ic_ir={check.ic_ir:.3f}  sharpe={result.sharpe:.2f}  "
            f"calmar={result.calmar:.2f}  max_drawdown={result.max_drawdown:.2%}  "
            f"final_equity={result.equity_curve.iloc[-1]:.4f}"
        )

    return results
