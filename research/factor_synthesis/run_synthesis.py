"""关卡2 · M1：合成方案对比（选择段估方向，验证段比较）。

要回答的问题：**按 regime state 选因子再合成，是否比不看 regime 的做法更好？**

参与比较的方案（README §4）：

| 方案 | 每根 bar 的分数 | 候选因子来源 |
|---|---|---|
| G0 全局等权 | 全局因子方向对齐后等权 | `config.GLOBAL_FACTORS`：阶段一不看 regime 选出（完整 IC 序列的 |t|>=3 + |IC_IR| Top-K）、关卡1 全历史去冗余 |
| L0 并集等权 | 各 state 名单的并集，方向对齐后等权 | `config.all_factors()` |
| L2-<维度> 路由等权 | 当前 bar 所处 state 的名单，按该 state 的方向等权；state 未知/名单为空时退回 L0 | `config.REGIME_FACTOR_SETS[维度]` |

另外把每个候选因子单独作为参照（`kind=single`），用来看合成是否真的比最强的单因子更好。

三段切分（`research/research_config.json` 的 `window`）：

- **选择段** `research_start ~ validation_start`：候选名单就是在这一段上选出来的（阶段一 + 关卡1），
  这里只在这一段上估计每个因子的方向（IC 符号）。这一段上的方案表现是**样本内**的，只作参考；
- **验证段** `validation_start ~ research_end`：名单和方向都已固定，对所有方案来说都是没见过的数据，
  **方案之间的比较以这一段为准**；
- holdout 本脚本完全不碰——选定方案后再单独验收一次（README §6.4）。

选择段末尾去掉 `horizon_bars + execution_delay_bars` 根 bar 再估方向：这几根 bar 的标签会伸进验证段。

每个因子的处理顺序跟阶段一、关卡1 完全一致：原始分数 → 可流通性掩码 → 剥离 Beta/Size 取残差 →
截面排名。合成用的是残差分数（研究的每一步都基于残差，实盘也必须用同一个口径）。

产出（`results/`）：
- `01_scheme_comparison.csv`：方案（含单因子参照）× 段 的 IC 统计 + 分数稳定性（换手预警）；
- `02_validation_ic_by_state.csv`：各合成方案在验证段、分 regime state 的条件 IC；
- `03_factor_signs.csv`：选择段上估出的每个因子的全局方向 / 各 state 方向。

运行前先带 `--refresh-synthesis-candidates` 跑过 `run_research.sh`（或手动跑 `refresh_candidates.py`），
保证 `config.py` 里的两份候选池是最新的。
    CH_HOST=... CH_PASSWORD=... python research/factor_synthesis/run_synthesis.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.custom  # noqa: F401  触发内置三大家族的 @register_alpha 注册
import sherpa.alpha.tradingview  # noqa: F401
import sherpa.alpha.worldquant  # noqa: F401
from sherpa.alpha import registry
from sherpa.backtest.regime_screening import regime_report
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.metrics.factor import conditional_ic_summary, rank_ic
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

import config
from data import (
    END_TIME,
    EXECUTION_DELAY_BARS,
    HORIZON_BARS,
    INTERVAL,
    START_TIME,
    VALIDATION_START,
    label_forward_returns,
    load_universe_panel,
)
from signals import (
    cross_sectional_rank,
    equal_weight_composite,
    estimate_signs,
    estimate_state_signs,
    routed_composite,
    score_autocorr,
    segment_masks,
    summarize_ic,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
COMPARISON_PATH = _RESULTS_DIR / "01_scheme_comparison.csv"
BY_STATE_PATH = _RESULTS_DIR / "02_validation_ic_by_state.csv"
SIGNS_PATH = _RESULTS_DIR / "03_factor_signs.csv"


def _check_candidates() -> None:
    if not config.GLOBAL_FACTORS or not config.all_factors():
        raise SystemExit(
            "factor_synthesis/config.py 的候选池是空的：先带 --refresh-synthesis-candidates 跑 run_research.sh"
            "（或手动跑 refresh_candidates.py）"
        )


def _residual_scores(names: list[str], panel, mask: pd.DataFrame, exposures: dict) -> dict[str, pd.DataFrame]:
    """原始分数 → 可流通性掩码 → 剥离 Beta/Size 取残差，跟阶段一、关卡1 的处理顺序一致。"""
    histories: dict[str, pd.DataFrame] = {}
    started = time.monotonic()
    for i, name in enumerate(names, 1):
        history = registry.get(name)().compute(panel)
        histories[name] = neutralize(history.where(mask), exposures)
        print(f"  [{i}/{len(names)}] {name}，已用时 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)
    return histories


def _rows_for(scheme: str, kind: str, n_factors: int, ic: pd.Series, autocorr: pd.Series, segments: dict) -> list[dict]:
    rows = []
    for segment, mask in segments.items():
        stats = summarize_ic(ic[mask.reindex(ic.index, fill_value=False)])
        rows.append({
            "scheme": scheme,
            "kind": kind,
            "n_factors": n_factors,
            "segment": segment,
            **stats,
            "score_autocorr": float(autocorr[mask.reindex(autocorr.index, fill_value=False)].mean()),
        })
    return rows


def main() -> None:
    _check_candidates()
    regime_factors = config.all_factors()
    all_names = list(dict.fromkeys(regime_factors + list(config.GLOBAL_FACTORS)))
    print(f"候选因子：G0 全局 {len(config.GLOBAL_FACTORS)} 个，regime 名单并集 {len(regime_factors)} 个，合计去重 {len(all_names)} 个")

    print(f"\n正在从 ClickHouse 拉取研究段 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线（验证段从 {VALIDATION_START} 开始）……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")
    print(f"IC 标签：持有 {HORIZON_BARS} 根 bar、执行延迟 {EXECUTION_DELAY_BARS} 根 bar（research_config.json 的 label 一节）")

    mask = tradable_mask(panel.quote_volume, panel.trades_count)
    forward_returns = label_forward_returns(panel).where(mask)
    regime = regime_report(panel, benchmark_symbol=config.REGIME_BENCHMARK_SYMBOL)
    exposures = default_style_exposures(panel, benchmark_symbol=config.REGIME_BENCHMARK_SYMBOL)

    print("\n正在计算候选因子的残差分数……")
    residuals = _residual_scores(all_names, panel, mask, exposures)
    ranked = {name: cross_sectional_rank(score) for name, score in residuals.items()}
    ic_by_factor = {name: rank_ic(score, forward_returns) for name, score in residuals.items()}

    selection, validation = segment_masks(
        panel.index, pd.Timestamp(VALIDATION_START, tz="UTC"), purge_bars=HORIZON_BARS + EXECUTION_DELAY_BARS
    )
    segments = {"selection(样本内参考)": selection, "validation(方案比较)": validation}
    print(f"选择段 {int(selection.sum())} 根 bar（已去掉边界 {HORIZON_BARS + EXECUTION_DELAY_BARS} 根），验证段 {int(validation.sum())} 根 bar")

    global_signs = estimate_signs(ic_by_factor, selection, min_samples=config.SIGN_MIN_SAMPLES_GLOBAL)

    print("\n正在合成各方案的分数……")
    schemes: dict[str, tuple[pd.DataFrame, int]] = {}
    schemes["G0 全局等权"] = (equal_weight_composite(ranked, global_signs, config.GLOBAL_FACTORS), len(config.GLOBAL_FACTORS))
    l0 = equal_weight_composite(ranked, global_signs, regime_factors)
    schemes["L0 并集等权"] = (l0, len(regime_factors))

    sign_rows = [{"factor": name, "scope": "global", "sign": sign} for name, sign in global_signs.items()]
    for dim in config.ROUTING_DIMENSIONS:
        state_factors = config.REGIME_FACTOR_SETS.get(dim, {})
        state_signs = estimate_state_signs(
            ic_by_factor, selection, regime[dim], state_factors, global_signs, min_samples=config.SIGN_MIN_SAMPLES_STATE
        )
        schemes[f"L2-{dim} 路由等权"] = (routed_composite(ranked, state_signs, state_factors, regime[dim], fallback=l0), len(regime_factors))
        sign_rows += [
            {"factor": name, "scope": f"{dim}.{state}", "sign": sign}
            for state, signs in state_signs.items() for name, sign in signs.items()
        ]

    comparison: list[dict] = []
    by_state: list[dict] = []
    for scheme, (scores, n_factors) in schemes.items():
        ic = rank_ic(scores, forward_returns)
        comparison += _rows_for(scheme, "composite", n_factors, ic, score_autocorr(scores), segments)
        ic_validation = ic[validation.reindex(ic.index, fill_value=False)]
        for dim in config.ROUTING_DIMENSIONS:
            table = conditional_ic_summary(ic_validation, regime[dim]).rename_axis("state").reset_index()
            for row in table.to_dict("records"):
                by_state.append({"scheme": scheme, "dimension": dim, **row})

    for name in all_names:
        sign = global_signs.get(name, 0.0)
        if sign == 0.0:
            continue
        signed = ranked[name] * sign
        comparison += _rows_for(f"single:{name}", "single", 1, ic_by_factor[name] * sign, score_autocorr(signed), segments)

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    comparison_df = pd.DataFrame(comparison)
    comparison_df.to_csv(COMPARISON_PATH, index=False)
    pd.DataFrame(by_state).to_csv(BY_STATE_PATH, index=False)
    pd.DataFrame(sign_rows).to_csv(SIGNS_PATH, index=False)

    view = comparison_df[comparison_df["segment"].str.startswith("validation")]
    view = view.sort_values(["kind", "ic_ir"], ascending=[True, False])
    columns = ["scheme", "n_factors", "samples", "ic_mean", "ic_ir", "t_stat", "win_rate", "score_autocorr"]
    print("\n== 验证段（方案比较以此为准）：合成方案 ==")
    print(view[view["kind"] == "composite"][columns].round(4).to_string(index=False))
    print("\n== 验证段：单因子参照（前 5） ==")
    print(view[view["kind"] == "single"][columns].head(5).round(4).to_string(index=False))
    print(f"\n结果已写入：\n  {COMPARISON_PATH}\n  {BY_STATE_PATH}\n  {SIGNS_PATH}")


if __name__ == "__main__":
    main()
