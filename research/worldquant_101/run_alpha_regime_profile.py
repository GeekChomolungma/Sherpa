"""世坤101研究项目·Regime 全历史体检第二步：把已经通过 `run_screening.py` 第一层筛选的
alpha，逐个在 `regime_report.csv` 的四个维度上做条件 IC 切片，产出"alpha × 维度 × 状态"的
长表体检结果。

跟 `run_screening.py`/`run_regime_report.py` 完全解耦——regime 和 alpha 各自独立算完，这里
只是把两条已经落盘的旁路结果拿来对齐，不重新碰 ClickHouse 之外的任何东西（除了要重新
`alpha.compute(panel)` 拿 `ic_series`，因为 `screening_report.csv` 里只落了汇总标量，没有
逐 bar 的 IC 序列）。对应架构分层：
`sherpa.metrics.factor.conditional_ic_summary`（纯统计）
-> `sherpa.backtest.regime_screening.profile_alphas_by_regime`（批量入口）
-> 这里（具体项目跑批 + 落盘）。

运行前先跑过 `run_screening.py`（产出 `screening_report.csv`）和 `run_regime_report.py`
（产出 `regime_report.csv`），再跑：
    CH_HOST=... CH_PASSWORD=... python research/worldquant_101/run_alpha_regime_profile.py
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.worldquant  # noqa: F401  import 触发 @register_alpha，把 101 个 alpha 都注册进 registry
from sherpa.alpha import registry
from sherpa.backtest.regime_screening import profile_alphas_by_regime, regime_report
from sherpa.metrics.factor import rank_ic

from data import END_TIME, INTERVAL, START_TIME, load_universe_panel

SCREENING_REPORT_PATH = "screening_report.csv"
BENCHMARK_SYMBOL = "BTCUSDT"
OUTPUT_PATH = "regime_alpha_profile.csv"


def _passed_qualified_names() -> list[str]:
    screening = pd.read_csv(SCREENING_REPORT_PATH, index_col=0)
    passed = screening[screening["passed"]]
    return list(passed.index)


def main() -> None:
    qualified_names = _passed_qualified_names()
    print(f"从 {SCREENING_REPORT_PATH} 读到 {len(qualified_names)} 个通过第一层筛选的 alpha")
    if not qualified_names:
        print("没有通过第一层筛选的 alpha，无需继续，先去跑 run_screening.py")
        return

    print(f"\n正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    forward_returns = panel.close.pct_change().shift(-1)

    print(f"\n正在对 {len(qualified_names)} 个 alpha 重算 ic_series……")
    ic_series_by_alpha: dict[str, pd.Series] = {}
    for qualified_name in qualified_names:
        alpha = registry.get(qualified_name)()
        history = alpha.compute(panel)
        ic_series_by_alpha[qualified_name] = rank_ic(history, forward_returns)

    print("正在计算 regime 报告矩阵……")
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    print("正在做条件 IC 切片体检……")
    profile = profile_alphas_by_regime(ic_series_by_alpha, regime)
    profile.to_csv(OUTPUT_PATH, index=False)
    print(f"\n完整 alpha × regime 体检长表已写入 research/worldquant_101/{OUTPUT_PATH}")

    print("\n== 每个 alpha 在各维度上 ic_ir 波动最大的一档（跟 ALL 基线差距最大） ==")
    # 用 merge 而不是把 (alpha, dimension) 设成索引再相减——非 ALL 的那部分一个 (alpha,
    # dimension) 对应好几个 state（bull/bear/neutral...），设成索引后是非唯一 MultiIndex，
    # 没法直接跟按 (alpha, dimension) 唯一索引的 baseline 做逐元素对齐相减。
    baseline = profile.loc[profile["state"] == "ALL", ["alpha", "dimension", "ic_ir"]]
    baseline = baseline.rename(columns={"ic_ir": "baseline_ic_ir"})
    non_baseline = profile[profile["state"] != "ALL"].dropna(subset=["ic_ir"])
    non_baseline = non_baseline.merge(baseline, on=["alpha", "dimension"], how="left")
    non_baseline["ic_ir_gap"] = (non_baseline["ic_ir"] - non_baseline["baseline_ic_ir"]).abs()
    top_gap = non_baseline.sort_values("ic_ir_gap", ascending=False).head(20)
    print(top_gap.to_string(index=False))


if __name__ == "__main__":
    main()
