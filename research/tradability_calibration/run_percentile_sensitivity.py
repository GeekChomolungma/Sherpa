"""tradability_calibration 研究项目·Study 2：只测 `min_percentile` 这一个参数（把绝对
地板 `min_quote_volume`/`min_trades_count` 关掉，隔离出相对排名单独的效果），看每一期
实际有多少 symbol 通过流通性筛选——尤其要抓"整个截面集体过冷、通过数量塌缩到个位数"的
时段。之前在合成数据的烟雾测试里发现过这个坑：symbol 数量少或者全市场都很冷清时，纯相对
排名会失效（"最活跃的 80%"如果全市场当时都很冷清，依然是一堆死币）。这一步就是看真实数据
里这个坑到底存不存在、多严重，从而决定 Study 3 的绝对地板要设多严。

同 Study 1 的方法论红线：不看任何 alpha/IC，只看通过筛选的 symbol 数量本身。

运行前先设好连接环境变量：
    CH_HOST=... CH_PASSWORD=... python research/tradability_calibration/run_percentile_sensitivity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from sherpa.metrics.tradability import DEFAULT_LOOKBACK, tradable_mask

from data import END_TIME, INTERVAL, START_TIME, load_universe_panel

RESULTS_DIR = Path(__file__).parent / "results"
CANDIDATE_PERCENTILES = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
# 少于这个绝对数字，就认为当期截面"塌缩"到了危险地步（截面样本太小，秩相关没有意义）。
LOW_PASS_ABS_THRESHOLD = 20


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    RESULTS_DIR.mkdir(exist_ok=True)
    active_symbol_count = panel.close.notna().sum(axis=1)

    rows = []
    pass_count_by_percentile: dict[float, pd.Series] = {}
    for p in CANDIDATE_PERCENTILES:
        mask = tradable_mask(
            panel.quote_volume,
            panel.trades_count,
            lookback=DEFAULT_LOOKBACK,
            seasoning_period=DEFAULT_LOOKBACK,
            min_percentile=p,
            min_quote_volume=0.0,
            min_trades_count=0.0,
        )
        pass_count = mask.sum(axis=1)
        pass_count_by_percentile[p] = pass_count

        denom = active_symbol_count.replace(0, pd.NA)
        pass_fraction = (pass_count / denom).dropna()
        below_threshold = pass_count < LOW_PASS_ABS_THRESHOLD

        rows.append(
            {
                "min_percentile": p,
                "mean_pass_count": pass_count.mean(),
                "median_pass_count": pass_count.median(),
                "min_pass_count": pass_count.min(),
                "min_pass_count_time": pass_count.idxmin(),
                "p5_pass_count": pass_count.quantile(0.05),
                "mean_pass_fraction": pass_fraction.mean() if not pass_fraction.empty else float("nan"),
                "bars_below_abs_threshold": int(below_threshold.sum()),
                "pct_bars_below_abs_threshold": float(below_threshold.mean()),
            }
        )
        print(
            f"min_percentile={p:.1f}: 平均通过 {pass_count.mean():.1f} 个，"
            f"最少通过 {pass_count.min()} 个（{pass_count.idxmin()}），"
            f"塌缩(<{LOW_PASS_ABS_THRESHOLD})根数={int(below_threshold.sum())}"
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(RESULTS_DIR / "percentile_sensitivity_summary.csv", index=False)

    timeseries = pd.DataFrame(pass_count_by_percentile)
    timeseries.columns = [f"pass_count_p{p}" for p in CANDIDATE_PERCENTILES]
    timeseries.to_csv(RESULTS_DIR / "percentile_sensitivity_timeseries.csv")

    print(f"\n汇总表 + 逐期通过数量时间序列已写入 {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
