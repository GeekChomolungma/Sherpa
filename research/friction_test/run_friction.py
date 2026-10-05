"""关卡3 · 换手摩擦与组合构建测试：把关卡2 的冻结配方变成仓位，扣费回测。

**输入是流水线的标准配方集**（`research/_shared/handoff.py`）：读研究线的 `<研究线>/handoff/synthesis.json`
——关卡2 真跑时是它比较过的方案，关卡2 透传时是候选集直接变成的等权配方（`直通·` 前缀）。关卡3 不关心配方
是谁产出的，所有研究线都必须过这一关。明细产出写到 `<研究线>/results/friction/`。

要回答的问题：**关卡2 的合成分数变成真实持仓、扣掉手续费和滑点之后，还剩多少？用什么组合构建方式最划算？**

对每个 case（配方集里的每个配方）× 每种权重映射
（`config.WEIGHTINGS`，Top-K + 排名迟滞）× 每种调仓频率（`config.REBALANCE_EVERY`，全仓调仓）
跑一遍 `run_vectorized_backtest`
（零成本，得到逐 bar 毛收益和换手；打分 → 目标仓位 → 回测 → 分段绩效这条链在 `sherpa.backtest.score_backtest`，
跟 ML 探索实验 `research/ml_training/evaluation.py` 共用），再对每种成本假设（`config.COST_MODELS`）扣费：
`净收益 = 毛收益 − CostModel.cost(换手)`。成本只从收益里扣、不影响仓位（权重是资金占比），所以这跟
直接用该 CostModel 跑回测的结果完全相同，只是省掉了重复的逐 bar 递推。

时间切分（`research/research_config.json` 的 `window`）：

- 回测覆盖整个研究段 `research_start ~ research_end`，持仓路径是连续的一条；
- **验证段** `validation_start ~ research_end`：配方（因子、方向、权重）都在选择段上定好，对这一段是没见过的
  数据。**case × 组合构建方式之间的比较、验收红线都以这一段为准**；
- **选择段**的表现是样本内的，只作参考；
- holdout 本脚本完全不碰——关卡3 选定组合构建方式后，冻结的整份配方到阶段二在 holdout 上只跑一次。

注意：这里的网格搜索本身会"用掉"一部分验证段——在验证段上挑最好的 (case, 映射, 频率) 组合，挑出来的
结果天然偏乐观。所以结论应该看**稳健的区域**（一片参数都不错），而不是网格里最高的那一格；最终的
无偏估计留给 holdout。

执行时点：IC 标签的执行延迟是 `execution_delay_bars` 根 bar（信号在 t 收盘算出，t+delay 收盘才成交），
回测的 `shift = 1 + execution_delay_bars` 与之对齐，赚的正是 IC 标签衡量的那段收益。

产出（`<研究线>/results/friction/`）：
- `00_case_consistency.csv`：重建出来的每个 case 的合成分数，按关卡2 同一口径重算的 RankIC_IR vs 配方里带的
  `reference`（关卡2 报告的数字）——两者应一致（浮点误差内），不一致说明配方重建或数据口径出了问题，后面的
  回测结论都不可信。透传产出的配方不带 `reference`，这一列是空的、`consistent` 也是空的（不适用，不是不一致）；
- `01_friction_summary.csv`：case × 映射 × 调仓频率 × 成本假设 × 段 的完整绩效长表；
- `02_validation_base_cost.csv`：验证段、`BASE_COST` 下每种 (case, 映射, 频率) 一行，附其它成本假设下的
  净 Sharpe（`net_sharpe[<成本名>]`）和验收红线判定，按净 Sharpe 从高到低排序——**先看这张**；
- `03_validation_net_equity.csv`：验证段、`BASE_COST` 下净 Sharpe 前 `EQUITY_TOP_N` 名组合的净值曲线（宽表，
  列 = 组合），方便画图。全部组合都存会有几十 MB；
- `case_grids/<case>.csv`：每个 case 一张验证段净 Sharpe 的二维截面（行 = 映射，列 = 成本假设 × 调仓频率，
  `zero` 那几列就是毛 Sharpe），从 `01_friction_summary.csv` pivot 出来，看一个 case 的稳健区域用。

怎么读这些结果，见同目录的 `RESULT_READING.md`。

回测按 case 分到多个进程并行（每个 case 的整套网格在一个进程里跑完），进程数见 `MAX_WORKERS`。

运行前先跑完研究线的上游阶段（关卡2 或它的透传），保证配方交接文件存在：

    CH_HOST=... CH_PASSWORD=... python research/friction_test/run_friction.py --track <研究线>
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.custom  # noqa: F401  触发内置三大家族的 @register_alpha 注册
import sherpa.alpha.tradingview  # noqa: F401
import sherpa.alpha.worldquant  # noqa: F401
from sherpa.backtest.regime_screening import regime_report
from sherpa.backtest.residual import ScorePreprocessor, residual_scores
from sherpa.backtest.attribution import attribute, period_stats, style_factor_returns
from sherpa.backtest.score_backtest import cost_segment_rows, run_score_backtest
from sherpa.data.schema import interval_to_timedelta
from sherpa.metrics.factor import ic_summary, rank_ic

import config
from data import (
    BENCHMARK_SYMBOL,
    COST_VENUE,
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
    case_scores,
    cross_sectional_rank,
    segment_masks,
    target_path,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import handoff  # noqa: E402
from track import load_track  # noqa: E402

STAGE = "friction"
CONSISTENCY_FILE = "00_case_consistency.csv"
SUMMARY_FILE = "01_friction_summary.csv"
RANKING_FILE = "02_validation_base_cost.csv"
EQUITY_FILE = "03_validation_net_equity.csv"
CASE_GRIDS_DIR = "case_grids"
ROBUSTNESS_FILE = "04_robustness.csv"
ATTRIBUTION_FILE = "05_style_attribution.csv"
QUARTERLY_FILE = "06_quarterly.csv"

# 重算的验证段 IC_IR 跟关卡2 报告的差多少算"对不上"。同一份数据、同一套公式，理论上只有浮点误差；
# 放宽到 1e-3 是为了容忍 ClickHouse 里最近几根 bar 被补写 / 修订之类的数据漂移。
CONSISTENCY_TOLERANCE = 1e-3

# 03_validation_net_equity.csv 只存净 Sharpe 前几名组合的净值曲线。
EQUITY_TOP_N = 30
# 并行进程数：按 case 分任务，每个 worker 会收到一份该 case 的分数矩阵和全市场收盘价（各几十 MB）。
MAX_WORKERS = min(8, os.cpu_count() or 1)

KEYS = ["case", "weighting", "rebalance_every"]


def _check_config(recipes: handoff.RecipeSet, path: Path) -> None:
    if not recipes.recipes:
        raise SystemExit(
            f"{path} 里一个配方都没有：上游没有候选因子可用（阶段一显著因子为 0？可以在 track.json 的 "
            "report.min_abs_t 放宽门槛），或者关卡2 透传的 stages.synthesis.passthrough 全关了"
        )
    if config.BASE_COST not in config.COST_MODELS:
        raise SystemExit(f"BASE_COST={config.BASE_COST!r} 不在 COST_MODELS 里")


def _print_progress(i: int, total: int, name: str, elapsed: float) -> None:
    print(f"  [{i}/{total}] {name}，已用时 {elapsed / 60:.1f} 分钟", flush=True)


def _consistency_rows(
    scores: dict[str, pd.DataFrame], recipes: handoff.RecipeSet, forward_returns: pd.DataFrame, validation: pd.Series
) -> list[dict]:
    """重算每个配方的验证段 IC_IR，跟配方自带的 `reference.validation_ic_ir`（产出方报告的数字）比。

    没有 `reference` 的配方（透传产出、或者手写的）不适用这项检查：`consistent` 留空，不算不一致。
    `equivalent_to`：上游去重时合并进这个配方的其它配方名（它们的回测结果就是这个配方的结果）。
    """
    rows = []
    for case, score in scores.items():
        ic = rank_ic(score, forward_returns)
        recomputed = ic_summary(ic[validation.reindex(ic.index, fill_value=False)]).ic_ir
        expected = recipes.recipes[case].get("reference", {}).get("validation_ic_ir", float("nan"))
        has_reference = pd.notna(expected)
        rows.append({
            "case": case,
            "recomputed_validation_ic_ir": recomputed,
            "reported_validation_ic_ir": expected,
            "abs_diff": abs(recomputed - expected) if has_reference else float("nan"),
            "consistent": bool(abs(recomputed - expected) <= CONSISTENCY_TOLERANCE) if has_reference else None,
            "equivalent_to": " | ".join(recipes.recipes[case].get("equivalent_to", [])),
        })
    return rows


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="关卡3：配方 × 组合构建 × 成本的扣费回测")
    parser.add_argument("--track", required=True, help="研究线 id（research/alpha_research/<id>/）或目录")
    args = parser.parse_args(argv)
    track = load_track(args.track)
    input_path = track.handoff_path(handoff.INPUT_STAGE[STAGE])
    recipes = handoff.read_recipes(input_path, expect_track=track.id)
    print(f"研究线 {track.id} · 关卡3；输入配方集 {input_path}（producer={recipes.producer}）")
    _check_config(recipes, input_path)
    track.import_alpha_modules()
    results_dir = track.stage_results_dir(STAGE)

    factor_names = recipes.factor_names()
    grid = [(w, r) for w in config.WEIGHTINGS for r in config.REBALANCE_EVERY]
    print(f"{len(recipes.recipes)} 个 case，共用到 {len(factor_names)} 个因子；组合构建网格 {len(grid)} 种 "
          f"（{len(config.WEIGHTINGS)} 种映射 × {len(config.REBALANCE_EVERY)} 种调仓频率），"
          f"成本假设 {len(config.COST_MODELS)} 种")

    print(f"\n正在从 ClickHouse 拉取研究段 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线（验证段从 {VALIDATION_START} 开始）……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")
    shift = 1 + EXECUTION_DELAY_BARS
    print(f"执行时点：信号延迟 {EXECUTION_DELAY_BARS} 根 bar 成交 → 回测 shift={shift}（IC 标签持有 {HORIZON_BARS} 根 bar）")
    print(f"成本口径（research_config.json 的 costs）：{COST_VENUE}，" + "，".join(f"{n}={m}" for n, m in config.COST_MODELS.items()))

    preprocessor = ScorePreprocessor.from_panel(
        panel, benchmark_symbol=BENCHMARK_SYMBOL, tradable=track.tradable, neutralize=track.neutralize
    )
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    print("\n正在计算因子的残差分数……")
    residuals, _ = residual_scores(factor_names, panel, preprocessor, progress=_print_progress)
    ranked = {name: cross_sectional_rank(score) for name, score in residuals.items()}
    scores = {case: case_scores(recipe, ranked, regime) for case, recipe in recipes.recipes.items()}

    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    segments = segment_masks(panel.index, validation_start)
    consistency = pd.DataFrame(_consistency_rows(
        scores, recipes, preprocessor.mask_labels(label_forward_returns(panel)), segments["validation(方案比较)"]
    ))
    results_dir.mkdir(parents=True, exist_ok=True)
    consistency.to_csv(results_dir / CONSISTENCY_FILE, index=False)
    print("\n== 配方重建一致性（重算的验证段 IC_IR vs 配方里带的关卡2 报告值；透传配方不适用） ==")
    print(consistency.round(4).to_string(index=False))
    if (consistency["consistent"] == False).any():  # noqa: E712  None（不适用）不算不一致
        print("\n[警告] 有 case 对不上关卡2 的结果：配方重建或数据口径有偏差，下面的回测结论要打折扣。"
              "常见原因：关卡2 的 results 是旧的（改了候选池没重跑）、或 research_config.json 改过。")

    periods_per_year = pd.Timedelta(days=365) / interval_to_timedelta(panel.interval)
    summary: list[dict] = []
    equity: dict[str, pd.Series] = {}
    base_nets: dict[str, pd.Series] = {}
    started = time.monotonic()
    print(f"\n正在跑 {len(scores) * len(grid)} 组回测（{len(scores)} 个 case 分到 {MAX_WORKERS} 个进程）……")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_run_case, case, score, panel.close, panel.interval, shift, grid, segments, periods_per_year): case
            for case, score in scores.items()
        }
        for done, future in enumerate(as_completed(futures), 1):
            rows, curves, nets = future.result()
            summary += rows
            equity.update(curves)
            base_nets.update(nets)
            print(f"  [{done}/{len(futures)}] {futures[future]} 完成，已用时 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)

    summary_df = pd.DataFrame(summary)
    summary_df["_segment_order"] = (~summary_df["segment"].str.startswith("validation")).astype(int)
    summary_df = summary_df.sort_values(
        ["_segment_order", "cost_model", "net_sharpe"], ascending=[True, True, False], na_position="last"
    ).drop(columns=["_segment_order"])
    summary_df.to_csv(results_dir / SUMMARY_FILE, index=False)

    ranking = _validation_ranking(summary_df)
    ranking.to_csv(results_dir / RANKING_FILE, index=False)
    top_labels = [_label(row) for row in ranking.head(EQUITY_TOP_N).to_dict("records")]
    pd.DataFrame({label: equity[label] for label in top_labels}).to_csv(results_dir / EQUITY_FILE)
    write_case_grids(summary_df, results_dir / CASE_GRIDS_DIR)

    robustness = _robustness(summary_df)
    robustness.to_csv(results_dir / ROBUSTNESS_FILE, index=False)
    print("\n正在算风格归因（BTC / 全市场 / 低波动 / 小市值 / 反转 / 动量）和分季度表现……")
    style = style_factor_returns(
        panel.close, panel.quote_volume, preprocessor.mask,
        interval=panel.interval, shift=shift, benchmark_symbol=BENCHMARK_SYMBOL,
    )
    attribution, quarterly = _attribution_and_quarterly(base_nets, style, validation_start, periods_per_year)
    attribution.to_csv(results_dir / ATTRIBUTION_FILE, index=False)
    quarterly.to_csv(results_dir / QUARTERLY_FILE, index=False)

    other_costs = [f"net_sharpe[{name}]" for name in config.COST_MODELS if name not in (config.BASE_COST, "zero")]
    columns = [*KEYS, "gross_sharpe", "net_sharpe", *other_costs,
               "net_max_drawdown", "turnover_per_bar", "turnover_decay", "breakeven_cost_bps", "passes_red_lines"]
    print(f"\n== 验证段 · 成本 {config.BASE_COST}：净 Sharpe 前 20 ==")
    print(ranking[columns].head(20).round(3).to_string(index=False))
    print(f"\n== 验证段 · 各 case 的最好组合（红线：净 Sharpe >= {config.MIN_NET_SHARPE}，换手衰减 < {config.MAX_TURNOVER_DECAY:.0%}） ==")
    print(ranking.drop_duplicates("case")[columns].round(3).to_string(index=False))
    print(f"\n== 稳健性（{config.BASE_COST}：全部组合的净 Sharpe 中位数、两段都为正的组合占比；选择段空仓 > "
          f"{config.ROBUSTNESS_MAX_FLAT:.0%} 的组合不计入） ==")
    print(robustness[robustness.cost_model == config.BASE_COST].drop(columns="cost_model").round(3).to_string(index=False))
    print(f"\n结果已写入 {results_dir}：{CONSISTENCY_FILE} / {SUMMARY_FILE} / {RANKING_FILE} / {EQUITY_FILE} / {CASE_GRIDS_DIR}/ / "
          f"{ROBUSTNESS_FILE} / {ATTRIBUTION_FILE} / {QUARTERLY_FILE}")


def write_case_grids(summary_df: pd.DataFrame, out_dir: Path) -> list[Path]:
    """每个 case 写一张验证段净 Sharpe 的二维截面：行 = 映射（`config.WEIGHTINGS` 的顺序），
    列 = `<成本假设>|every<N>`（成本按 `config.COST_MODELS` 的顺序、再按调仓频率）。

    只做 pivot、不重跑回测，所以也可以单独对已有的 `01_friction_summary.csv` 调用。写之前清空目录，
    避免 case 名单变了以后留下过期文件。文件名里 Windows 不允许的字符（如 `single:` 里的冒号）换成 `_`。
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("*.csv"):
        old.unlink()
    validation = summary_df[summary_df["segment"].str.startswith("validation")]
    costs = [c for c in config.COST_MODELS if c in set(validation["cost_model"])]
    written = []
    for case, rows in validation.groupby("case", sort=False):
        grid = rows.pivot_table(index="weighting", columns=["cost_model", "rebalance_every"], values="net_sharpe")
        grid = grid.reindex(index=[w for w in config.WEIGHTINGS if w in grid.index])
        grid = grid.reindex(columns=[(c, r) for c in costs for r in sorted(set(rows["rebalance_every"]))])
        grid.columns = [f"{cost}|every{rebalance}" for cost, rebalance in grid.columns]
        path = out_dir / (re.sub(r'[<>:"/\\|?*\s]+', "_", str(case)).strip("_") + ".csv")
        grid.round(4).to_csv(path, index_label="weighting")
        written.append(path)
    return written


def _label(row: dict[str, Any]) -> str:
    return f"{row['case']} | {row['weighting']} | every{row['rebalance_every']}"


def _run_case(
    case: str,
    score: pd.DataFrame,
    close: pd.DataFrame,
    interval: str,
    shift: int,
    grid: list[tuple[str, int]],
    segments: dict[str, pd.Series],
    periods_per_year: float,
) -> tuple[list[dict], dict[str, pd.Series]]:
    """一个 case 的整套网格（worker 进程里跑）：返回绩效长表的行、验证段 BASE_COST 下的净值曲线、
    全时段（从第一根有打分的 bar 起）BASE_COST 下的逐 bar 净收益（风格归因 / 分季度用）。

    打分 → 目标仓位 → 回测 → 分段绩效这条链在 `sherpa.backtest.score_backtest`（跟 ML 探索实验共用），这里只管网格。
    """
    rows: list[dict] = []
    curves: dict[str, pd.Series] = {}
    nets: dict[str, pd.Series] = {}
    # 分段从这个 case 第一根有打分的 bar 开始：模型 / 因子的 warm-up 期（比如 ML alpha 第一个模型之前）没有信号，
    # 算进选择段只会制造一大段"空仓"，拉低 Sharpe、让空仓比例失真
    scored = score.notna().any(axis=1)
    active_start = scored.idxmax() if scored.any() else score.index[-1]
    segments = {name: mask & (mask.index >= active_start) for name, mask in segments.items()}
    for weighting, rebalance in grid:
        # 目标权重路径先按时间顺序算好（缓冲带要参考上一期目标），回测只做恒等映射。
        targets = target_path(score, config.WEIGHTINGS[weighting], rebalance)
        gross, turnover = run_score_backtest(targets, close, interval, shift=shift, rebalance_every=rebalance)
        key = {"case": case, "weighting": weighting, "rebalance_every": rebalance}
        seg_nets: dict[tuple[str, str], pd.Series] = {}
        rows += [{**key, **row} for row in cost_segment_rows(
            gross, turnover, config.COST_MODELS, segments, periods_per_year=periods_per_year, net_curves=seg_nets
        )]
        for (cost_name, segment), net in seg_nets.items():
            if cost_name == config.BASE_COST and segment.startswith("validation"):
                curves[_label(key)] = (1.0 + net).cumprod()
        base_net = gross - turnover.map(config.COST_MODELS[config.BASE_COST].cost)
        nets[_label(key)] = base_net[base_net.index >= active_start]
    return rows, curves, nets


def _robustness(summary_df: pd.DataFrame) -> pd.DataFrame:
    """每个 case × 成本假设一行：全部组合（映射 × 调仓频率）在两段的净 Sharpe 中位数 / 为正占比，两段都为正的组合占比。

    看的是"一片参数区域都成立"，不是网格里最高的那一格——最高的那格往往是噪声挑出来的。选择段空仓比例超过
    `config.ROBUSTNESS_MAX_FLAT` 的组合不计入。
    """
    selection = summary_df[~summary_df["segment"].str.startswith("validation")]
    flat = selection[selection["cost_model"] == "zero"].set_index(KEYS)["flat_bar_fraction"]
    usable = flat[flat <= config.ROBUSTNESS_MAX_FLAT].index
    rows = []
    for (case, cost), group in summary_df.groupby(["case", "cost_model"], sort=False):
        wide = group.set_index(KEYS).pivot(columns="segment", values="net_sharpe")
        wide = wide.loc[wide.index.intersection(usable)]
        sel = wide[[c for c in wide.columns if not c.startswith("validation")][0]] if len(wide.columns) else pd.Series(dtype=float)
        val = wide[[c for c in wide.columns if c.startswith("validation")][0]] if len(wide.columns) else pd.Series(dtype=float)
        rows.append({
            "case": case, "cost_model": cost, "n_combos": len(wide),
            "selection_median": sel.median(), "validation_median": val.median(),
            "selection_positive_frac": (sel > 0).mean(), "validation_positive_frac": (val > 0).mean(),
            "both_positive_frac": ((sel > 0) & (val > 0)).mean(),
        })
    return pd.DataFrame(rows)


def _attribution_and_quarterly(
    nets: dict[str, pd.Series], style: pd.DataFrame, validation_start: pd.Timestamp, periods_per_year: float
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """每个 (case, 映射, 调仓频率) 的 BASE_COST 净收益：分段做风格归因（`05`），按季度统计（`06`）。"""
    attribution, quarterly = [], []
    for label, net in nets.items():
        case, weighting, rebalance = [part.strip() for part in label.split("|")]
        key = {"case": case, "weighting": weighting, "rebalance_every": int(rebalance.removeprefix("every"))}
        for segment, in_segment in (("selection", net.index < validation_start), ("validation", net.index >= validation_start)):
            attribution.append({**key, "segment": segment,
                                **attribute(net[in_segment], style, periods_per_year=periods_per_year)})
        stats = period_stats(net, periods_per_year=periods_per_year)
        full = stats["return"].dropna()  # 不足 60 根 bar 的季度（开头 / 结尾的零头）不计
        row = {**key, "quarters": len(full), "positive_quarter_frac": float((full > 0).mean()) if len(full) else float("nan")}
        row.update({f"sharpe[{p}]": v for p, v in stats["sharpe"].items()})
        row.update({f"return[{p}]": v for p, v in stats["return"].items()})
        quarterly.append(row)
    return pd.DataFrame(attribution), pd.DataFrame(quarterly)


def _validation_ranking(summary_df: pd.DataFrame) -> pd.DataFrame:
    """验证段、BASE_COST 下每种组合一行，附其它成本假设下的净 Sharpe 和验收红线判定。"""
    validation = summary_df[summary_df["segment"].str.startswith("validation")]
    base = validation[validation["cost_model"] == config.BASE_COST].copy()
    for name in config.COST_MODELS:
        if name in (config.BASE_COST, "zero"):
            continue
        other = validation[validation["cost_model"] == name][KEYS + ["net_sharpe"]]
        base = base.merge(other.rename(columns={"net_sharpe": f"net_sharpe[{name}]"}), on=KEYS, how="left")
    base["passes_red_lines"] = (base["net_sharpe"] >= config.MIN_NET_SHARPE) & (base["turnover_decay"] < config.MAX_TURNOVER_DECAY)
    return base.sort_values("net_sharpe", ascending=False, na_position="last").reset_index(drop=True)


if __name__ == "__main__":
    main()
