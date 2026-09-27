"""关卡3 · 换手摩擦与组合构建测试：把关卡2 的冻结配方变成仓位，扣费回测。

要回答的问题：**关卡2 的合成分数变成真实持仓、扣掉手续费和滑点之后，还剩多少？用什么组合构建方式最划算？**

对每个 case（`config.CASES`，由 `refresh_candidates.py` 从关卡2 的 results 生成）× 每种权重映射
（`config.WEIGHTINGS`，Top-K + 排名迟滞）× 每种调仓频率（`config.REBALANCE_EVERY`，全仓调仓）
跑一遍 `run_vectorized_backtest`
（零成本，得到逐 bar 毛收益和换手），再对每种成本假设（`config.COST_MODELS`）扣费：
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

产出（`results/`）：
- `00_case_consistency.csv`：重建出来的每个 case 的合成分数，按关卡2 同一口径重算的 RankIC_IR vs 关卡2 报告的
  数字——两者应一致（浮点误差内），不一致说明配方重建或数据口径出了问题，后面的回测结论都不可信；
- `01_friction_summary.csv`：case × 映射 × 调仓频率 × 成本假设 × 段 的完整绩效长表；
- `02_validation_base_cost.csv`：验证段、`BASE_COST` 下每种 (case, 映射, 频率) 一行，附其它成本假设下的
  净 Sharpe（`net_sharpe[<成本名>]`）和验收红线判定，按净 Sharpe 从高到低排序——**先看这张**；
- `03_validation_net_equity.csv`：验证段、`BASE_COST` 下净 Sharpe 前 `EQUITY_TOP_N` 名组合的净值曲线（宽表，
  列 = 组合），方便画图。全部组合都存会有几十 MB；
- `case_grids/<case>.csv`：每个 case 一张验证段净 Sharpe 的二维截面（行 = 映射，列 = 成本假设 × 调仓频率，
  `zero` 那几列就是毛 Sharpe），从 `01_friction_summary.csv` pivot 出来，看一个 case 的稳健区域用。

怎么读这些结果，见同目录的 `RESULT_READING.md`。

回测按 case 分到多个进程并行（每个 case 的整套网格在一个进程里跑完），进程数见 `MAX_WORKERS`。

运行前先跑关卡2，再跑 `refresh_candidates.py`（或 `run_research.sh --refresh-friction-cases`）：

    CH_HOST=... CH_PASSWORD=... python research/friction_test/run_friction.py
"""

from __future__ import annotations

import os
import re
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.custom  # noqa: F401  触发内置三大家族的 @register_alpha 注册
import sherpa.alpha.tradingview  # noqa: F401
import sherpa.alpha.worldquant  # noqa: F401
from sherpa.alpha import registry
from sherpa.backtest.cost_model import ZeroCostModel
from sherpa.backtest.regime_screening import regime_report
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.backtest.vectorized import run_vectorized_backtest
from sherpa.data.schema import BarPanel, interval_to_timedelta
from sherpa.metrics.factor import ic_summary, rank_ic
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

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
    required_factors,
    segment_masks,
    segment_stats,
    target_path,
)

_RESULTS_DIR = Path(__file__).resolve().parent / "results"
CONSISTENCY_PATH = _RESULTS_DIR / "00_case_consistency.csv"
SUMMARY_PATH = _RESULTS_DIR / "01_friction_summary.csv"
RANKING_PATH = _RESULTS_DIR / "02_validation_base_cost.csv"
EQUITY_PATH = _RESULTS_DIR / "03_validation_net_equity.csv"
CASE_GRIDS_DIR = _RESULTS_DIR / "case_grids"
SYNTH_COMPARISON = Path(__file__).resolve().parent.parent / "factor_synthesis" / "results" / "01_scheme_comparison.csv"

# 重算的验证段 IC_IR 跟关卡2 报告的差多少算"对不上"。同一份数据、同一套公式，理论上只有浮点误差；
# 放宽到 1e-3 是为了容忍 ClickHouse 里最近几根 bar 被补写 / 修订之类的数据漂移。
CONSISTENCY_TOLERANCE = 1e-3

# 03_validation_net_equity.csv 只存净 Sharpe 前几名组合的净值曲线。
EQUITY_TOP_N = 30
# 并行进程数：按 case 分任务，每个 worker 会收到一份该 case 的分数矩阵和全市场收盘价（各几十 MB）。
MAX_WORKERS = min(8, os.cpu_count() or 1)

KEYS = ["case", "weighting", "rebalance_every"]


@dataclass(frozen=True)
class _PricePanel:
    """只带 `close` + `interval` 的轻量 panel：`run_vectorized_backtest` 只用到这两个字段。

    完整的 `BarPanel` 有十来个 (T, N) 字段，发给每个 worker 进程要序列化几百 MB，这里只传用得到的部分。
    """

    close: pd.DataFrame
    interval: str


def _check_config() -> None:
    if not config.CASES:
        raise SystemExit(
            "friction_test/config.py 的 CASES 是空的：先跑关卡2，再跑 refresh_candidates.py"
            "（或 run_research.sh --refresh-friction-cases）"
        )
    if config.BASE_COST not in config.COST_MODELS:
        raise SystemExit(f"BASE_COST={config.BASE_COST!r} 不在 COST_MODELS 里")


def _residual_scores(names: list[str], panel, mask: pd.DataFrame, exposures: dict) -> dict[str, pd.DataFrame]:
    """原始分数 → 可流通性掩码 → 剥离 Beta/Size 取残差，跟阶段一、关卡1、关卡2 的处理顺序一致。"""
    histories: dict[str, pd.DataFrame] = {}
    started = time.monotonic()
    for i, name in enumerate(names, 1):
        history = registry.get(name)().compute(panel)
        histories[name] = neutralize(history.where(mask), exposures)
        print(f"  [{i}/{len(names)}] {name}，已用时 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)
    return histories


def _consistency_rows(scores: dict[str, pd.DataFrame], forward_returns: pd.DataFrame, validation: pd.Series) -> list[dict]:
    reported = {}
    if SYNTH_COMPARISON.exists():
        table = pd.read_csv(SYNTH_COMPARISON)
        table = table[table["segment"].str.startswith("validation")]
        reported = dict(zip(table["scheme"], table["ic_ir"]))
    rows = []
    for case, score in scores.items():
        ic = rank_ic(score, forward_returns)
        recomputed = ic_summary(ic[validation.reindex(ic.index, fill_value=False)]).ic_ir
        expected = reported.get(case, float("nan"))
        rows.append({
            "case": case,
            "recomputed_validation_ic_ir": recomputed,
            "gate2_validation_ic_ir": expected,
            "abs_diff": abs(recomputed - expected) if pd.notna(expected) else float("nan"),
            "consistent": bool(pd.notna(expected) and abs(recomputed - expected) <= CONSISTENCY_TOLERANCE),
        })
    return rows


def main() -> None:
    _check_config()
    factor_names = required_factors(config.CASES)
    grid = [(w, r) for w in config.WEIGHTINGS for r in config.REBALANCE_EVERY]
    print(f"{len(config.CASES)} 个 case，共用到 {len(factor_names)} 个因子；组合构建网格 {len(grid)} 种 "
          f"（{len(config.WEIGHTINGS)} 种映射 × {len(config.REBALANCE_EVERY)} 种调仓频率），"
          f"成本假设 {len(config.COST_MODELS)} 种")

    print(f"\n正在从 ClickHouse 拉取研究段 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线（验证段从 {VALIDATION_START} 开始）……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")
    shift = 1 + EXECUTION_DELAY_BARS
    print(f"执行时点：信号延迟 {EXECUTION_DELAY_BARS} 根 bar 成交 → 回测 shift={shift}（IC 标签持有 {HORIZON_BARS} 根 bar）")
    print(f"成本口径（research_config.json 的 costs）：{COST_VENUE}，" + "，".join(f"{n}={m}" for n, m in config.COST_MODELS.items()))

    mask = tradable_mask(panel.quote_volume, panel.trades_count)
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)
    exposures = default_style_exposures(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    print("\n正在计算因子的残差分数……")
    residuals = _residual_scores(factor_names, panel, mask, exposures)
    ranked = {name: cross_sectional_rank(score) for name, score in residuals.items()}
    scores = {case: case_scores(recipe, ranked, regime) for case, recipe in config.CASES.items()}

    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    segments = segment_masks(panel.index, validation_start)
    consistency = pd.DataFrame(_consistency_rows(scores, label_forward_returns(panel).where(mask), segments["validation(方案比较)"]))
    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    consistency.to_csv(CONSISTENCY_PATH, index=False)
    print("\n== 配方重建一致性（重算的验证段 IC_IR vs 关卡2 报告值） ==")
    print(consistency.round(4).to_string(index=False))
    if not consistency["consistent"].all():
        print("\n[警告] 有 case 对不上关卡2 的结果：配方重建或数据口径有偏差，下面的回测结论要打折扣。"
              "常见原因：关卡2 的 results 是旧的（改了候选池没重跑）、或 research_config.json 改过。")

    periods_per_year = pd.Timedelta(days=365) / interval_to_timedelta(panel.interval)
    prices = _PricePanel(close=panel.close, interval=panel.interval)
    summary: list[dict] = []
    equity: dict[str, pd.Series] = {}
    started = time.monotonic()
    print(f"\n正在跑 {len(scores) * len(grid)} 组回测（{len(scores)} 个 case 分到 {MAX_WORKERS} 个进程）……")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(_run_case, case, score, prices, shift, grid, segments, periods_per_year): case
            for case, score in scores.items()
        }
        for done, future in enumerate(as_completed(futures), 1):
            rows, curves = future.result()
            summary += rows
            equity.update(curves)
            print(f"  [{done}/{len(futures)}] {futures[future]} 完成，已用时 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)

    summary_df = pd.DataFrame(summary)
    summary_df["_segment_order"] = (~summary_df["segment"].str.startswith("validation")).astype(int)
    summary_df = summary_df.sort_values(
        ["_segment_order", "cost_model", "net_sharpe"], ascending=[True, True, False], na_position="last"
    ).drop(columns=["_segment_order"])
    summary_df.to_csv(SUMMARY_PATH, index=False)

    ranking = _validation_ranking(summary_df)
    ranking.to_csv(RANKING_PATH, index=False)
    top_labels = [_label(row) for row in ranking.head(EQUITY_TOP_N).to_dict("records")]
    pd.DataFrame({label: equity[label] for label in top_labels}).to_csv(EQUITY_PATH)
    write_case_grids(summary_df)

    other_costs = [f"net_sharpe[{name}]" for name in config.COST_MODELS if name not in (config.BASE_COST, "zero")]
    columns = [*KEYS, "gross_sharpe", "net_sharpe", *other_costs,
               "net_max_drawdown", "turnover_per_bar", "turnover_decay", "breakeven_cost_bps", "passes_red_lines"]
    print(f"\n== 验证段 · 成本 {config.BASE_COST}：净 Sharpe 前 20 ==")
    print(ranking[columns].head(20).round(3).to_string(index=False))
    print(f"\n== 验证段 · 各 case 的最好组合（红线：净 Sharpe >= {config.MIN_NET_SHARPE}，换手衰减 < {config.MAX_TURNOVER_DECAY:.0%}） ==")
    print(ranking.drop_duplicates("case")[columns].round(3).to_string(index=False))
    print(f"\n结果已写入：\n  {CONSISTENCY_PATH}\n  {SUMMARY_PATH}\n  {RANKING_PATH}\n  {EQUITY_PATH}\n  {CASE_GRIDS_DIR}\\")


def write_case_grids(summary_df: pd.DataFrame, out_dir: Path = CASE_GRIDS_DIR) -> list[Path]:
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
    prices: _PricePanel,
    shift: int,
    grid: list[tuple[str, int]],
    segments: dict[str, pd.Series],
    periods_per_year: float,
) -> tuple[list[dict], dict[str, pd.Series]]:
    """一个 case 的整套网格（worker 进程里跑）：返回绩效长表的行 + 验证段 BASE_COST 下的净值曲线。"""
    rows: list[dict] = []
    curves: dict[str, pd.Series] = {}
    for weighting, rebalance in grid:
        # 目标权重路径先按时间顺序算好（缓冲带要参考上一期目标），回测只做恒等映射。
        targets = target_path(score, config.WEIGHTINGS[weighting], rebalance)
        result = run_vectorized_backtest(
            targets, cast(BarPanel, prices), lambda row: row, ZeroCostModel(), shift=shift, rebalance_every=rebalance,
        )
        gross, turnover = result.returns, result.turnover
        key = {"case": case, "weighting": weighting, "rebalance_every": rebalance}
        for cost_name, cost_model in config.COST_MODELS.items():
            net = gross - turnover.map(cost_model.cost)
            for segment, in_segment in segments.items():
                in_rows = in_segment.reindex(net.index, fill_value=False)
                rows.append({
                    **key,
                    "cost_model": cost_name,
                    "segment": segment,
                    **segment_stats(gross[in_rows], turnover[in_rows], net[in_rows], periods_per_year=periods_per_year),
                })
                if cost_name == config.BASE_COST and segment.startswith("validation"):
                    curves[_label(key)] = (1.0 + net[in_rows]).cumprod()
    return rows, curves


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
