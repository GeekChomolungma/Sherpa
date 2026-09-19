"""世坤101研究项目·Regime 全历史体检第一步：对真实 ClickHouse 全市场数据打 regime 标签，
产出"行=时间，列=trend/volatility/dispersion/liquidity 四维度 + regime_label 结论"的报告矩阵。

这一步只打标、落盘，不碰任何 alpha——regime 和 alpha 是两条独立算出来、最后才对齐的旁路
（`research/REGIME_ALPHA_EVALUATION_WORKFLOW.md` 的方法论），对应分层是：
`sherpa.metrics.regime`（纯打标） -> `sherpa.backtest.regime_screening`（BarPanel 适配）
-> 这里（具体项目跑批 + 落盘）。

`regime_label` 目前是四个维度状态原样拼接，不做归并（有几十种组合），留到接上具体 alpha 的
条件 IC 表现后再决定怎么合并。

运行方式同 `run_screening.py`：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/worldquant_101/run_regime_report.py
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from sherpa.backtest.regime_screening import regime_report

from data import END_TIME, INTERVAL, START_TIME, load_universe_panel

REPORT_PATH = "regime_report.csv"
BENCHMARK_SYMBOL = "BTCUSDT"


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    report = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    report.to_csv(REPORT_PATH)
    print(f"\n完整 regime 报告矩阵已写入 research/alpha_research/worldquant_101/{REPORT_PATH}")

    n_known = report["regime_label"].notna().sum()
    print(f"\n共 {len(report)} 根 bar，其中 {n_known} 根已脱离滚动窗口 warm-up、有完整四维度标签")

    print("\n== 各维度状态分布 ==")
    for col in ["trend", "volatility", "dispersion", "liquidity"]:
        print(f"\n{col}:")
        print(report[col].value_counts(dropna=False).to_string())

    print(f"\n== regime_label 组合分布（共 {report['regime_label'].nunique()} 种组合） ==")
    print(report["regime_label"].value_counts().to_string())


if __name__ == "__main__":
    main()
