"""tradability_calibration 研究项目·Study 3：结合 Study 1 的分位数分布，测几组候选绝对
地板（`min_quote_volume`/`min_trades_count`），看"通过率被这道地板压得很低"的 symbol
集合跟"Study 1 里终身成交额最低的一批"重合度高不高——重合度高说明这个地板确实在挡真正的
死币，不是误伤活跃但天生盘子小的币种。

用"逐期通过率"而不是"历史上有没有哪怕一次通过"来判定一个 symbol 是不是被地板挡住——典型
成交量刚好卡在地板附近的死币，几年历史里偶尔一天异常放量就能侥幸超过门槛一次，"从未通过"
这个全有全无的标准太严格，会把这种情况误判成"没被挡住"。

候选地板直接从 `run_distribution_study.py` 产出的 `volume_distribution_summary.csv` 里
取分位数（P1/P5/P10），不凭空拍数字——运行前必须先跑过 `run_distribution_study.py`。

同 Study 1/2 的方法论红线：不看任何 alpha/IC，只看跟"死币候选名单"的重合度这一个跟因子
表现完全无关的独立证据。这一步只测绝对地板本身的效果，`min_percentile` 固定为 0（关掉
相对排名，避免两个参数的效果混在一起看不清楚）。

运行前先设好连接环境变量，并且先跑过 `run_distribution_study.py`：
    CH_HOST=... CH_PASSWORD=... python research/tradability_calibration/run_floor_sensitivity.py
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
CANDIDATE_SOURCE_PERCENTILES = [0.01, 0.05, 0.10, 0.25, 0.5, 0.75]
# Study 1 里终身成交额中位数最低的这么多个 symbol，当独立的"死币候选名单"用来做重合度检查。
N_KNOWN_DEAD_FOR_OVERLAP_CHECK = 200
# 通过率低于这个比例，才算"被这道地板实质挡住"——不能用"一次都没通过过"当标准：一个典型
# 成交量刚好卡在地板附近的死币，在几年历史里偶尔一天异常放量就能侥幸超过门槛一次，"从未
# 通过"这个全有全无的标准太严格，会把这种情况误判成"没被挡住"。
FLAGGED_PASS_FRACTION_THRESHOLD = 0.05


def load_candidate_floors() -> pd.DataFrame:
    """候选地板 = Study 1 分位数分布表里的 P1/P5/P10，外加一行 0（不设地板）做基线对照。"""
    dist_path = RESULTS_DIR / "volume_distribution_summary.csv"
    if not dist_path.exists():
        raise SystemExit(f"找不到 {dist_path}，请先跑 run_distribution_study.py")
    dist = pd.read_csv(dist_path)

    candidates = [{"source_percentile": None, "min_quote_volume": 0.0, "min_trades_count": 0.0}]
    for p in CANDIDATE_SOURCE_PERCENTILES:
        qv = dist.loc[(dist["metric"] == "rolling_quote_volume") & (dist["percentile"] == p), "value"]
        tc = dist.loc[(dist["metric"] == "rolling_trades_count") & (dist["percentile"] == p), "value"]
        if qv.empty or tc.empty:
            continue
        candidates.append(
            {"source_percentile": p, "min_quote_volume": float(qv.iloc[0]), "min_trades_count": float(tc.iloc[0])}
        )
    return pd.DataFrame(candidates)


def known_dead_candidates() -> set[str]:
    lifetime_path = RESULTS_DIR / "symbol_lifetime_summary.csv"
    if not lifetime_path.exists():
        raise SystemExit(f"找不到 {lifetime_path}，请先跑 run_distribution_study.py")
    lifetime = pd.read_csv(lifetime_path)
    return set(lifetime.head(N_KNOWN_DEAD_FOR_OVERLAP_CHECK)["symbol"])


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    RESULTS_DIR.mkdir(exist_ok=True)
    candidate_floors = load_candidate_floors()
    known_dead = known_dead_candidates()
    print(f"Study 1 里终身成交额最低的 {N_KNOWN_DEAD_FOR_OVERLAP_CHECK} 个 symbol（独立死币候选）：")
    print(sorted(known_dead))

    rows = []
    for _, cand in candidate_floors.iterrows():
        mask = tradable_mask(
            panel.quote_volume,
            panel.trades_count,
            lookback=DEFAULT_LOOKBACK,
            seasoning_period=DEFAULT_LOOKBACK,
            min_percentile=0.0,
            min_quote_volume=cand["min_quote_volume"],
            min_trades_count=cand["min_trades_count"],
        )
        pass_fraction = mask.mean(axis=0)
        flagged = set(pass_fraction[pass_fraction < FLAGGED_PASS_FRACTION_THRESHOLD].index)
        overlap = flagged & known_dead

        rows.append(
            {
                "source_percentile": cand["source_percentile"],
                "min_quote_volume": cand["min_quote_volume"],
                "min_trades_count": cand["min_trades_count"],
                "symbols_flagged": len(flagged),
                "overlap_with_known_dead": len(overlap),
                "overlap_fraction_of_known_dead": (len(overlap) / len(known_dead)) if known_dead else float("nan"),
                "known_dead_pass_fraction_mean": pass_fraction.reindex(known_dead).mean() if known_dead else float("nan"),
            }
        )
        print(
            f"地板(quote_volume>={cand['min_quote_volume']:.4g}, trades_count>={cand['min_trades_count']:.4g}): "
            f"{len(flagged)} 个 symbol 通过率 < {FLAGGED_PASS_FRACTION_THRESHOLD:.0%}，"
            f"跟独立死币候选重合 {len(overlap)}/{len(known_dead)}，"
            f"已知死币平均通过率={pass_fraction.reindex(known_dead).mean():.4f}"
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(RESULTS_DIR / "floor_sensitivity_summary.csv", index=False)
    print(f"\n汇总表已写入 {RESULTS_DIR}/floor_sensitivity_summary.csv")


if __name__ == "__main__":
    main()
