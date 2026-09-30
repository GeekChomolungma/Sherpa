"""关卡2 · M1：合成方案对比（选择段估方向，验证段比较）。

**输入是流水线的标准候选集，输出是标准配方集**（`research/_shared/handoff.py`）：读研究线的
`<研究线>/handoff/orthogonalization.json`，把参与比较的方案连同方向 / 权重冻结成配方写进
`<研究线>/handoff/synthesis.json` 给关卡3。明细产出写到 `<研究线>/results/synthesis/`。研究线 `track.json`
把关卡2 设成 `passthrough` 时，不取数、不比较，直接把候选集变成等权配方（`passthrough.py`）。

要回答的问题：**按 regime state 选因子再合成，是否比不看 regime 的做法更好？**

参与比较的方案（README §4）：

| 方案 | 每根 bar 的分数 | 候选因子来源 |
|---|---|---|
| G0 全局等权 | 全局因子方向对齐后等权 | 候选集的全局名单：阶段一不看 regime 选出（完整 IC 序列的 |t|>=3 + |IC_IR| Top-K）、关卡1 全历史去冗余 |
| L1 全局 ICIR 加权 | 同 G0 的因子，按选择段 IC_IR（带符号）加权 | 同 G0；回答"加权比等权有没有增量"，也是以后滚动重训的基本形态 |
| L0 并集等权 | 各 state 名单的并集，方向对齐后等权 | 候选集各 state 名单的并集 |
| L2-<维度> 路由等权 | 当前 bar 所处 state 的名单，按该 state 的方向等权；state 未知/名单为空时退回 L0 | 候选集里该维度各 state 的名单 |

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

产出（`<研究线>/results/synthesis/`）：
- `01_scheme_comparison.csv`：方案（含单因子参照）× 段 的 IC 统计 + 分数稳定性（换手预警）；
  已排序：验证段在前、合成方案在前，同组内按 IC_IR 从高到低；
- `02_validation_ic_by_state.csv`：各合成方案在验证段、分 regime state 的条件 IC；
- `03_factor_weights.csv`：各方案实际使用的每个因子的方向与权重（选择段上估出）；
- `04_yearly_ic.csv`：G0 / L1 合成分数和 G0 各因子**按自然年**的 IC 统计（稳健性检验 R1）——
  看因子的预测力是否随年份衰减、老数据是否还有价值。覆盖整个研究段，最后两年落在验证段里。

交给关卡3 的配方集：合成方案默认全收 + 选择段最强的单因子参照（`config.HANDOFF_*`），每个配方带
`reference`（验证段 / 选择段 IC_IR、分数自相关），关卡3 用它做重建一致性检查。

    CH_HOST=... CH_PASSWORD=... python research/factor_synthesis/run_synthesis.py --track <研究线>
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.custom  # noqa: F401  触发内置三大家族的 @register_alpha 注册
import sherpa.alpha.tradingview  # noqa: F401
import sherpa.alpha.worldquant  # noqa: F401
from sherpa.backtest.regime_screening import regime_report
from sherpa.backtest.residual import ScorePreprocessor, residual_scores
from sherpa.metrics.factor import conditional_ic_summary, rank_ic

import config
from data import (
    BENCHMARK_SYMBOL,
    END_TIME,
    EXECUTION_DELAY_BARS,
    HORIZON_BARS,
    INTERVAL,
    START_TIME,
    VALIDATION_START,
    label_forward_returns,
    load_universe_panel,
)
from passthrough import direct_recipes
from signals import (
    cross_sectional_rank,
    equal_weight_composite,
    estimate_icir_weights,
    estimate_signs,
    estimate_state_signs,
    routed_composite,
    score_autocorr,
    segment_masks,
    summarize_ic,
    weighted_composite,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import handoff  # noqa: E402
from track import load_track  # noqa: E402

STAGE = "synthesis"
COMPARISON_FILE = "01_scheme_comparison.csv"
BY_STATE_FILE = "02_validation_ic_by_state.csv"
WEIGHTS_FILE = "03_factor_weights.csv"
YEARLY_FILE = "04_yearly_ic.csv"


def _check_candidates(candidates: handoff.CandidateSet, path: Path) -> None:
    if not candidates.global_set.names or not candidates.regime_union():
        raise SystemExit(
            f"{path} 的候选池不完整（全局名单 {len(candidates.global_set.names)} 个、state 名单并集 "
            f"{len(candidates.regime_union())} 个）：关卡2 的 G0 / L 系列方案两份都要。上游显著因子太少时，"
            "可以把这条研究线的关卡2 设成 passthrough"
        )


def _scope_of(scheme: str) -> str:
    """方案名 → `03_factor_weights.csv` 里的 scope 前缀，例如 "L2-volatility 路由等权" → "L2-volatility"。"""
    return scheme.split(" ", 1)[0]


def recipes_from_results(
    comparison: pd.DataFrame, weights: pd.DataFrame, *, max_composites: Optional[int], singles: int
) -> dict[str, dict[str, Any]]:
    """本关比较结果（`01_scheme_comparison` / `03_factor_weights` 两张表）→ 交给关卡3 的冻结配方。

    - 合成方案按验证段 IC_IR 排序全收（或前 `max_composites` 个）；配方直接取 `raw_weight`，不重估：
      `G0` / `L1` / `L0` 取 scope 同名的行；`L2-<维度>` 按 `L2-<维度>.<state>` 分组，fallback 用 `L0`；
    - 单因子参照按**选择段** IC_IR 取前 `singles` 个，方向取全局方向（`G0` / `L0` 里的符号）；
    - 每个配方带 `reference`：本关报告的验证段 / 选择段 IC_IR 和验证段分数自相关，关卡3 拿来核对重建是否一致。
    """
    scopes: dict[str, dict[str, float]] = defaultdict(dict)
    for row in weights.itertuples(index=False):
        if float(row.raw_weight) != 0.0:
            scopes[row.scope][row.factor] = float(row.raw_weight)
    validation = comparison[comparison["segment"].str.startswith("validation")].set_index("scheme")
    selection = comparison[comparison["segment"].str.startswith("selection")].set_index("scheme")

    def reference(scheme: str) -> dict[str, float]:
        return {
            "validation_ic_ir": float(validation.at[scheme, "ic_ir"]),
            "selection_ic_ir": float(selection.at[scheme, "ic_ir"]),
            "validation_score_autocorr": float(validation.at[scheme, "score_autocorr"]),
        }

    recipes: dict[str, dict[str, Any]] = {}
    composites = validation[validation["kind"] == "composite"].sort_values("ic_ir", ascending=False)
    if max_composites is not None:
        composites = composites.head(max_composites)
    for scheme in composites.index:
        scope = _scope_of(scheme)
        if scope.startswith("L2-"):
            states = {key.split(".", 1)[1]: w for key, w in scopes.items() if key.startswith(f"{scope}.")}
            if not states or "L0" not in scopes:
                raise RuntimeError(f"方案 {scheme!r} 的权重不全（states={list(states)}，L0 {'有' if 'L0' in scopes else '缺'}）")
            recipe = {"kind": "routed", "dimension": scope[len("L2-"):], "states": states, "fallback": scopes["L0"]}
        else:
            recipe = {"kind": "static", "weights": scopes[scope]}
        recipes[scheme] = {**recipe, "reference": reference(scheme)}

    global_signs = {**scopes.get("L0", {}), **scopes.get("G0", {})}
    single_rows = selection[selection["kind"] == "single"].sort_values("ic_ir", ascending=False).head(singles)
    for scheme in single_rows.index:
        name = scheme.split(":", 1)[1]
        sign = 1.0 if global_signs[name] > 0 else -1.0
        recipes[scheme] = {"kind": "static", "weights": {name: sign}, "reference": reference(scheme)}
    return recipes


def _print_progress(i: int, total: int, name: str, elapsed: float) -> None:
    print(f"  [{i}/{total}] {name}，已用时 {elapsed / 60:.1f} 分钟", flush=True)


def _weight_rows(scope: str, weights: dict[str, float]) -> list[dict]:
    """一个方案实际用的权重：sign = 方向，weight_share = |w_i| / Σ|w|（该方案内的占比）。"""
    total = sum(abs(w) for w in weights.values())
    return [
        {
            "scope": scope,
            "factor": name,
            "sign": (weight > 0) - (weight < 0),
            "raw_weight": weight,
            "weight_share": abs(weight) / total if total else 0.0,
        }
        for name, weight in weights.items()
    ]


def _yearly_rows(name: str, ic: pd.Series, validation_start: pd.Timestamp) -> list[dict]:
    """按自然年分组的 IC 统计（复用 conditional_ic_summary，分组标签换成年份）。"""
    clean = ic.dropna()
    years = pd.Series(clean.index.year.astype(str), index=clean.index)
    table = conditional_ic_summary(clean, years, label_horizon=HORIZON_BARS).drop(index="ALL")
    rows = []
    for year, row in table.iterrows():
        in_year = clean.index.year == int(year)
        segment = (
            "validation" if clean.index[in_year].min() >= validation_start
            else "selection" if clean.index[in_year].max() < validation_start
            else "selection+validation"
        )
        rows.append({"scheme": name, "year": int(year), "segment": segment, **row.to_dict()})
    return rows


def _rows_for(scheme: str, kind: str, n_factors: int, ic: pd.Series, autocorr: pd.Series, segments: dict) -> list[dict]:
    rows = []
    for segment, mask in segments.items():
        stats = summarize_ic(ic[mask.reindex(ic.index, fill_value=False)], label_horizon=HORIZON_BARS)
        rows.append({
            "scheme": scheme,
            "kind": kind,
            "n_factors": n_factors,
            "segment": segment,
            **stats,
            "score_autocorr": float(autocorr[mask.reindex(autocorr.index, fill_value=False)].mean()),
        })
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="关卡2：合成方案对比，产出交给关卡3 的配方集")
    parser.add_argument("--track", required=True, help="研究线 id（research/alpha_research/<id>/）或目录")
    args = parser.parse_args(argv)
    track = load_track(args.track)
    input_path = track.handoff_path(handoff.INPUT_STAGE[STAGE])
    candidates = handoff.read_candidates(input_path, expect_track=track.id)
    print(f"研究线 {track.id} · 关卡2 模式：{track.gate_mode(STAGE)}；输入候选集 {input_path}（producer={candidates.producer}）")

    if track.gate_mode(STAGE) == "passthrough":
        recipes = direct_recipes(candidates, track.synthesis_passthrough, track_id=track.id)
        out = handoff.write(track.handoff_path(STAGE), recipes)
        print(f"透传：候选集直接变成 {len(recipes.recipes)} 个等权配方（等效配方已合并），写入 {out}")
        for name, recipe in recipes.recipes.items():
            merged = recipe.get("equivalent_to")
            print(f"  {name}" + (f"（等效于：{'、'.join(merged)}）" if merged else ""))
        return

    _check_candidates(candidates, input_path)
    track.import_alpha_modules()
    global_factors = candidates.global_set.names
    regime_factor_sets = {dim: {state: c.names for state, c in states.items()} for dim, states in candidates.regime_sets.items()}
    routing_dimensions = candidates.dimensions
    regime_factors = candidates.regime_union()
    all_names = list(dict.fromkeys(regime_factors + list(global_factors)))
    print(f"候选因子：G0 全局 {len(global_factors)} 个，regime 名单并集 {len(regime_factors)} 个，合计去重 {len(all_names)} 个")

    print(f"\n正在从 ClickHouse 拉取研究段 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线（验证段从 {VALIDATION_START} 开始）……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")
    print(f"IC 标签：持有 {HORIZON_BARS} 根 bar、执行延迟 {EXECUTION_DELAY_BARS} 根 bar（research_config.json 的 label 一节）")

    preprocessor = ScorePreprocessor.from_panel(
        panel, benchmark_symbol=BENCHMARK_SYMBOL, tradable=track.tradable, neutralize=track.neutralize
    )
    forward_returns = preprocessor.mask_labels(label_forward_returns(panel))
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    print("\n正在计算候选因子的残差分数……")
    residuals, _ = residual_scores(all_names, panel, preprocessor, progress=_print_progress)
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
    schemes["G0 全局等权"] = (equal_weight_composite(ranked, global_signs, global_factors), len(global_factors))
    l1_weights = estimate_icir_weights(
        ic_by_factor, selection, global_factors, min_samples=config.SIGN_MIN_SAMPLES_GLOBAL
    )
    schemes["L1 全局ICIR加权"] = (weighted_composite(ranked, l1_weights, global_factors), len(global_factors))
    l0 = equal_weight_composite(ranked, global_signs, regime_factors)
    schemes["L0 并集等权"] = (l0, len(regime_factors))

    weight_rows = _weight_rows("G0", {name: global_signs[name] for name in global_factors})
    weight_rows += _weight_rows("L1", l1_weights)
    weight_rows += _weight_rows("L0", {name: global_signs[name] for name in regime_factors})
    for dim in routing_dimensions:
        state_factors = regime_factor_sets.get(dim, {})
        state_signs = estimate_state_signs(
            ic_by_factor, selection, regime[dim], state_factors, global_signs, min_samples=config.SIGN_MIN_SAMPLES_STATE
        )
        schemes[f"L2-{dim} 路由等权"] = (routed_composite(ranked, state_signs, state_factors, regime[dim], fallback=l0), len(regime_factors))
        for state, signs in state_signs.items():
            weight_rows += _weight_rows(f"L2-{dim}.{state}", dict(signs))

    comparison: list[dict] = []
    by_state: list[dict] = []
    for scheme, (scores, n_factors) in schemes.items():
        ic = rank_ic(scores, forward_returns)
        comparison += _rows_for(scheme, "composite", n_factors, ic, score_autocorr(scores), segments)
        ic_validation = ic[validation.reindex(ic.index, fill_value=False)]
        for dim in routing_dimensions:
            # ALL 行就是该方案验证段的整体 IC，01_scheme_comparison.csv 里已经有，这里只留各 state。
            table = conditional_ic_summary(ic_validation, regime[dim], label_horizon=HORIZON_BARS).drop(index="ALL").rename_axis("state").reset_index()
            for row in table.to_dict("records"):
                by_state.append({"scheme": scheme, "dimension": dim, **row})

    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    yearly: list[dict] = []
    for scheme in ("G0 全局等权", "L1 全局ICIR加权"):
        yearly += _yearly_rows(scheme, rank_ic(schemes[scheme][0], forward_returns), validation_start)
    for name in global_factors:
        sign = global_signs.get(name, 0.0)
        if sign != 0.0:
            yearly += _yearly_rows(f"single:{name}", ic_by_factor[name] * sign, validation_start)

    for name in all_names:
        sign = global_signs.get(name, 0.0)
        if sign == 0.0:
            continue
        signed = ranked[name] * sign
        comparison += _rows_for(f"single:{name}", "single", 1, ic_by_factor[name] * sign, score_autocorr(signed), segments)

    results_dir = track.stage_results_dir(STAGE)
    results_dir.mkdir(parents=True, exist_ok=True)
    # 写文件前排好序，打开 CSV 就是结论视角：验证段（方案比较以此为准）在前、选择段（样本内参考）在后；
    # 每段内合成方案在前、单因子参照在后；同组内按 IC_IR 从高到低。
    comparison_df = pd.DataFrame(comparison)
    comparison_df["_segment_order"] = (~comparison_df["segment"].str.startswith("validation")).astype(int)
    comparison_df["_kind_order"] = (comparison_df["kind"] != "composite").astype(int)
    comparison_df = comparison_df.sort_values(
        ["_segment_order", "_kind_order", "ic_ir"], ascending=[True, True, False], na_position="last"
    ).drop(columns=["_segment_order", "_kind_order"])
    weights_df = pd.DataFrame(weight_rows)
    comparison_df.to_csv(results_dir / COMPARISON_FILE, index=False)
    pd.DataFrame(by_state).to_csv(results_dir / BY_STATE_FILE, index=False)
    weights_df.to_csv(results_dir / WEIGHTS_FILE, index=False)
    yearly_df = pd.DataFrame(yearly)
    yearly_df.to_csv(results_dir / YEARLY_FILE, index=False)
    recipes = handoff.RecipeSet(
        track=track.id,
        producer=STAGE,
        recipes=recipes_from_results(
            comparison_df, weights_df, max_composites=config.HANDOFF_MAX_COMPOSITES, singles=config.HANDOFF_SINGLES
        ),
        meta={"input_producer": candidates.producer},
    )
    handoff_path = handoff.write(track.handoff_path(STAGE), recipes)

    view = comparison_df[comparison_df["segment"].str.startswith("validation")]
    view = view.sort_values(["kind", "ic_ir"], ascending=[True, False])
    columns = ["scheme", "n_factors", "samples", "ic_mean", "ic_ir", "t_stat", "win_rate", "score_autocorr"]
    print("\n== 验证段（方案比较以此为准）：合成方案 ==")
    print(view[view["kind"] == "composite"][columns].round(4).to_string(index=False))
    print("\n== 验证段：单因子参照（前 5） ==")
    print(view[view["kind"] == "single"][columns].head(5).round(4).to_string(index=False))
    print("\n== 分年 IC_IR（R1 稳健性：预测力是否随年份衰减） ==")
    pivot = yearly_df.pivot(index="scheme", columns="year", values="ic_ir")
    print(pivot.round(3).to_string())
    print("\n== L1 权重（选择段 IC_IR 占比） ==")
    l1_view = pd.DataFrame(_weight_rows("L1", l1_weights))[["factor", "sign", "raw_weight", "weight_share"]]
    print(l1_view.round(4).to_string(index=False))
    print(f"\n结果已写入 {results_dir}：{COMPARISON_FILE} / {BY_STATE_FILE} / {WEIGHTS_FILE} / {YEARLY_FILE}")
    print(f"交给关卡3 的配方集（{len(recipes.recipes)} 个）：{handoff_path}")


if __name__ == "__main__":
    main()
