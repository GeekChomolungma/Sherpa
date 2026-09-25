"""世坤101研究项目 · 第一步：批量跑 `run_alpha_check`（`sherpa.backtest.screening.screen_alphas`）。

拉真实 ClickHouse `data.START_TIME` ~ `data.END_TIME`（取自 `research/research_window.json` 的研究段）的
`data.INTERVAL`（当前是 4h）K 线，跑一遍全部 101 个已注册的世坤101因子，产出按 IC_IR 排序
的报告，写成 CSV 落盘。跟 `examples/alpha_screening_101.py` 是同一套调用方式，区别只是这里
接的是真实数据，不是合成数据。

这一步只做筛选，不算仓位/成本——通过的因子留给对应分类文件夹（`price_volume/`/
`momentum_reversal/`/...）下的 `run_vectorized.py` 去跑第二层。

`screen_alphas` 现在会先对每个因子的原始分数做中性化残差化（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`
§3.2，剔除 Beta/Size 被动暴露），再拿残差分数算 IC——`exposures` 用
`sherpa.backtest.style_exposure.default_style_exposures(panel)` 构造。

运行前先设好连接环境变量（同 `scripts/smoke_test_data_layer.py`）：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/worldquant_101/run_screening.py
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import sherpa.alpha.worldquant  # noqa: F401  import 触发 @register_alpha，把 101 个 alpha 都注册进 registry
from sherpa.alpha import registry
from sherpa.alpha.engine import AlphaEngine
from sherpa.backtest.screening import screen_alphas
from sherpa.backtest.style_exposure import default_style_exposures

from data import END_TIME, INTERVAL, START_TIME, load_universe_panel

IC_IR_THRESHOLD = 0.15
N_QUANTILES = 5
TOP_N = 20
REPORT_PATH = "screening_report.csv"


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    forward_returns = panel.close.pct_change().shift(-1)
    worldquant_alphas = [cls() for cls in registry.all(family="worldquant").values()]
    engine = AlphaEngine(worldquant_alphas)

    print("正在计算中性化用的风险暴露矩阵（Beta 对 BTCUSDT / Size 用 log(quote_volume)）……")
    exposures = default_style_exposures(panel)

    print(f"\n开始跑 {len(worldquant_alphas)} 个因子的第一层检验（残差分数）……")
    report = screen_alphas(
        engine, panel, forward_returns, n_quantiles=N_QUANTILES, ic_ir_threshold=IC_IR_THRESHOLD, exposures=exposures
    )

    passed = report.table[report.table["passed"]]
    print(f"\n算不出来的因子：{len(report.errors)} 个（缺行业分类/市值，占位不实现）")
    print(f"能算出结果：{len(report.table)} 个，通过第一层检验（IC_IR >= {IC_IR_THRESHOLD} 且分位数单调）：{len(passed)} 个")

    print(f"\n== IC_IR 排名前 {TOP_N} ==")
    print(report.table.head(TOP_N).to_string())

    if len(passed):
        print("\n通过第一层检验的因子：")
        print(passed.to_string())

    report.table.to_csv(REPORT_PATH)
    print(f"\n完整排行榜已写入 research/alpha_research/worldquant_101/{REPORT_PATH}")
    print("下一步：去对应分类文件夹跑 run_vectorized.py，对通过第一层的因子跑第二层向量化回测。")


if __name__ == "__main__":
    main()
