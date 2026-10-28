"""tradecraft 研究线的"只做多"回测：Top-K 只买入打分最高的币、不做空，跟等权基准比（关卡3 照常跑多空，这一步是附加的）。

    CH_HOST=... CH_PASSWORD=... python research/alpha_research/tradecraft/run_long_only.py <研究线目录>

为什么单独一步：关卡3 的 39 个组合都是多空对称的（`research/friction_test/`，ML / 世坤都靠它，不改）。只做多是另一种组合构建，
在这里按同一套零件算：打分 → 截面排名 → `sherpa.backtest.score_backtest.target_path`（跟关卡3 同一个 Top-K / 迟滞 / 调仓逻辑）
→ 只留多头一侧、放大到满仓（权重和 = 1）→ `run_score_backtest` → 按 `research_config.json` 的成本扣费（同关卡3）。

**只做多就不是市场中性了**：大盘涨跌直接进收益，牛市里只做多怎么都像赚钱。所以同时给两个等权基准（同样的调仓间隔、同样扣费）：

- `ew_scope`：等权买入流动性范围内的全部币（"闭眼买市场"）；
- `ew_pool`：等权买入这一期所有有打分的币（候选池）——Top-K 跑赢它，才说明池内排序有用，不只是"池子选得好"。

产出（`<run>/results*/long_only/`，格式跟关卡3 的 `07` / `08` / `bar_series.json` 相同，`research/viz/` 用 `--book long_only` 画）：

- `07_bar_gross_returns.csv` / `08_bar_turnover.csv`：每个组合（含两个基准）的逐 bar 毛收益 / 换手，列名 `<case> | <映射> | every<N>`；
- `bar_series.json`：成本 bps、验证段起点、默认组合；
- `01_summary.csv`：组合 × 成本 × 段的完整绩效（同关卡3 的 `segment_stats`），外加相对 `ew_scope` / `ew_pool` 的超额 Sharpe、年化超额、Beta；
- `04_robustness.csv`：每种成本下全部 Top-K 组合两段的净 Sharpe 中位数、两段都为正的占比，以及两个基准的 Sharpe。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "research" / "alpha_research" / "_pipeline"))
sys.path.insert(0, str(ROOT / "research" / "_shared"))
# evaluation.COST_MODELS：关卡3 同口径的成本（单测守住）。放在最后：ml_training/ 下也有一个 data.py，不能盖过 _pipeline/data.py
sys.path.append(str(ROOT / "research" / "ml_training"))

import evaluation  # noqa: E402
from data import BENCHMARK_SYMBOL, EXECUTION_DELAY_BARS, INTERVAL, RESEARCH_END, START_TIME, VALIDATION_START, load_universe_panel  # noqa: E402
from track import load_track  # noqa: E402

from sherpa.alpha import registry  # noqa: E402
from sherpa.backtest.residual import ScorePreprocessor, residual_score  # noqa: E402
from sherpa.backtest.score_backtest import cost_segment_rows, cross_sectional_rank, run_score_backtest, target_path  # noqa: E402
from sherpa.data.schema import interval_to_timedelta  # noqa: E402

STAGE = "long_only"
# 只做多的组合：Top-K（买前 k 名，跌出前 exit_k 才卖）× 调仓间隔（持有 2 / 3 根 bar = 8 / 12 小时）
WEIGHTINGS: dict[str, dict] = {
    "top5": {"method": "top_k", "k": 5, "exit_k": 5},
    "top5_exit10": {"method": "top_k", "k": 5, "exit_k": 10},
    "top10": {"method": "top_k", "k": 10, "exit_k": 10},
    "top10_exit20": {"method": "top_k", "k": 10, "exit_k": 20},
    "q10": {"method": "top_quantile", "q": 0.1, "exit_q": 0.1},
    "q20": {"method": "top_quantile", "q": 0.2, "exit_q": 0.2},
    "q20_exit40": {"method": "top_quantile", "q": 0.2, "exit_q": 0.4},
}
REBALANCE_EVERY: tuple[int, ...] = (2, 3)
DEFAULT_COMBO = ("top10_exit20", 3)
BASE_COST = evaluation.BASE_COST
BENCHMARKS = ("ew_scope", "ew_pool")


def long_targets(ranked: pd.DataFrame, spec: dict, rebalance_every: int) -> pd.DataFrame:
    """关卡3 的 Top-K 目标路径只留多头一侧，放大到满仓（多头权重和 = 1）。"""
    return target_path(ranked, spec, rebalance_every).clip(lower=0.0) * 2.0


def equal_weight_targets(members: pd.DataFrame, rebalance_every: int) -> pd.DataFrame:
    """等权买入 `members` 为 True 的币（只在调仓行算，非调仓行填 0，跟 target_path 同一口径）。"""
    weights = members.astype("float64")
    weights = weights.div(weights.sum(axis=1).where(lambda s: s > 0), axis=0).fillna(0.0)
    keep = np.zeros(len(weights), dtype=bool)
    keep[::rebalance_every] = True
    return weights.where(pd.Series(keep, index=weights.index), 0.0)


def excess_stats(net: pd.Series, bench: pd.Series, periods_per_year: float) -> dict[str, float]:
    excess = net - bench
    std = excess.std()
    beta = float(np.cov(net, bench)[0, 1] / bench.var()) if bench.var() > 0 else float("nan")
    return {
        "excess_sharpe": float(excess.mean() / std * np.sqrt(periods_per_year)) if std > 0 else float("nan"),
        "excess_ann_return": float(excess.mean() * periods_per_year),
        "beta": beta,
    }


def run_alpha(qualified_name: str, panel, preprocessor: ScorePreprocessor, out_dir: Path) -> pd.DataFrame:
    alpha = registry.get(qualified_name)()
    score = residual_score(alpha, panel, preprocessor)
    ranked = cross_sectional_rank(score)
    scored = score.notna().any(axis=1)
    start = scored.idxmax()
    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    index = panel.close.index
    segments = {
        "selection": pd.Series((index >= start) & (index < validation_start), index=index),
        "validation": pd.Series(index >= validation_start, index=index),
    }
    periods_per_year = pd.Timedelta(days=365) / interval_to_timedelta(panel.interval)
    shift = 1 + EXECUTION_DELAY_BARS
    scope = preprocessor.mask if preprocessor.mask is not None else panel.close.notna()

    gross: dict[str, pd.Series] = {}
    turnover: dict[str, pd.Series] = {}
    rows: list[dict] = []
    bench_net: dict[tuple[str, int, str], pd.Series] = {}
    for rebalance in REBALANCE_EVERY:
        for bench, members in (("ew_scope", scope), ("ew_pool", score.notna())):
            g, t = run_score_backtest(equal_weight_targets(members, rebalance), panel.close, panel.interval,
                                      shift=shift, rebalance_every=rebalance)
            label = f"benchmark | {bench} | every{rebalance}"
            gross[label], turnover[label] = g[g.index >= start], t[t.index >= start]
            nets: dict = {}
            rows += [{"case": "benchmark", "weighting": bench, "rebalance_every": rebalance, **r}
                     for r in cost_segment_rows(g, t, evaluation.COST_MODELS, segments, periods_per_year=periods_per_year, net_curves=nets)]
            for (cost, segment), net in nets.items():
                bench_net[(bench, rebalance, f"{cost}|{segment}")] = net
        for weighting, spec in WEIGHTINGS.items():
            g, t = run_score_backtest(long_targets(ranked, spec, rebalance), panel.close, panel.interval,
                                      shift=shift, rebalance_every=rebalance)
            label = f"long:{qualified_name} | {weighting} | every{rebalance}"
            gross[label], turnover[label] = g[g.index >= start], t[t.index >= start]
            nets = {}
            for r in cost_segment_rows(g, t, evaluation.COST_MODELS, segments, periods_per_year=periods_per_year, net_curves=nets):
                key = f"{r['cost_model']}|{r['segment']}"
                for bench in BENCHMARKS:
                    extra = excess_stats(nets[(r["cost_model"], r["segment"])], bench_net[(bench, rebalance, key)], periods_per_year)
                    r.update({f"{k}[{bench}]": v for k, v in extra.items()})
                rows.append({"case": f"long:{qualified_name}", "weighting": weighting, "rebalance_every": rebalance, **r})

    out_dir.mkdir(parents=True, exist_ok=True)
    labels = sorted(gross)
    pd.DataFrame({k: gross[k] for k in labels}).to_csv(out_dir / "07_bar_gross_returns.csv")
    pd.DataFrame({k: turnover[k] for k in labels}).to_csv(out_dir / "08_bar_turnover.csv")
    (out_dir / "bar_series.json").write_text(json.dumps({
        "description": "只做多 Top-K（多头满仓）+ 两个等权基准。07 = 逐 bar 毛收益，08 = 逐 bar 换手；净收益 = 毛收益 − 换手 × cost_bps / 10000",
        "cost_bps": {name: model.cost(1.0) * 10_000.0 for name, model in evaluation.COST_MODELS.items()},
        "base_cost": BASE_COST,
        "validation_start": validation_start.isoformat(),
        "shift": shift,
        "default_weighting": DEFAULT_COMBO[0],
        "default_rebalance_every": DEFAULT_COMBO[1],
        "columns": "<case> | <weighting> | every<rebalance_every>；case = long:<alpha> 或 benchmark",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = pd.DataFrame(rows)
    summary.to_csv(out_dir / "01_summary.csv", index=False)
    robust = []
    for cost in evaluation.COST_MODELS:
        part = summary[summary.cost_model == cost]
        top = part[part.case != "benchmark"].pivot_table(index=["weighting", "rebalance_every"], columns="segment", values="net_sharpe")
        exc = part[part.case != "benchmark"].pivot_table(index=["weighting", "rebalance_every"], columns="segment", values="excess_sharpe[ew_pool]")
        bench = part[part.case == "benchmark"].pivot_table(index="weighting", columns="segment", values="net_sharpe", aggfunc="median")
        robust.append({
            "cost_model": cost, "n_combos": len(top),
            "selection_median": top["selection"].median(), "validation_median": top["validation"].median(),
            "both_positive_frac": float(((top["selection"] > 0) & (top["validation"] > 0)).mean()),
            "excess_vs_pool_selection_median": exc["selection"].median(), "excess_vs_pool_validation_median": exc["validation"].median(),
            **{f"{b}_{seg}": bench.loc[b, seg] for b in BENCHMARKS for seg in ("selection", "validation")},
        })
    robust = pd.DataFrame(robust)
    robust.to_csv(out_dir / "04_robustness.csv", index=False)
    return robust


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法：python run_long_only.py <研究线目录>")
    track = load_track(sys.argv[1])
    track.import_alpha_modules()
    names = track.select_alphas()
    print(f"研究线 {track.id} · 只做多回测：{names}")
    started = time.monotonic()
    panel = load_universe_panel(end_time=RESEARCH_END)
    print(f"universe={len(panel.symbols)}，{len(panel.index)} 根 bar（{START_TIME} ~ {RESEARCH_END}），{time.monotonic() - started:.0f} 秒")
    preprocessor = ScorePreprocessor.from_panel(panel, benchmark_symbol=BENCHMARK_SYMBOL, tradable=track.tradable, neutralize=track.neutralize)
    out_dir = track.stage_results_dir(STAGE)
    for name in names:
        robust = run_alpha(name, panel, preprocessor, out_dir)
        print(f"\n== {name}（Top-K 只做多，{len(WEIGHTINGS)} 种映射 × 调仓每 {'/'.join(map(str, REBALANCE_EVERY))} 根）==")
        print(robust.round(3).to_string(index=False))
    print(f"\n-> {out_dir}（用时 {(time.monotonic() - started) / 60:.1f} 分钟）")


if __name__ == "__main__":
    main()
