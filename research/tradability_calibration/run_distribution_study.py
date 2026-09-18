"""tradability_calibration 研究项目·Study 1：先看真实数据里 quote_volume/trades_count
到底长什么样，不做任何假设、不碰任何 alpha/IC——这一步只提供独立于 alpha 表现的证据，供
后面 Study 2（`run_percentile_sensitivity.py`）/Study 3（`run_floor_sensitivity.py`）选
`min_percentile`/`min_quote_volume`/`min_trades_count` 时参考。

方法论红线（如实抄一遍免得以后忘）：`sherpa.metrics.tradability.tradable_mask` 这三个参数
的选择只能依据这里、以及 Study 2/3 里跟成交量/成交笔数本身相关的独立证据来定，不能拿
`run_alpha_regime_profile.py` 算出来的 IC_IR 好不好看去反推——那样等于用因子表现去调因子
表现赖以计算的输入数据，是彻头彻尾的数据窥探/过拟合。

输出三张表到 `results/`：
- `volume_distribution_summary.csv`：全体 (symbol, 时间) 点位上，滚动 quote_volume/
  trades_count 的分位数分布（用跟 `tradable_mask` 一样的 `DEFAULT_LOOKBACK`，口径对齐）。
  Study 3 会直接读这张表取候选绝对地板，不凭空拍数字。
- `symbol_lifetime_summary.csv`：每个 symbol 终身滚动成交额/成交笔数中位数，从低到高
  排序——唯一靠谱的地面真相来源，你可以拿这张表去肉眼核对"排在最底下这批是不是确实是
  你认识的死币"。Study 3 也会读这张表做重合度检查。
- `market_activity_over_time.csv`：全市场总成交额、当期有效 symbol 数随时间的变化——用来
  看非平稳性（成交规模这几年是不是涨了几个数量级），以及"某段时间整个截面 symbol 数量是
  不是特别少"（如果 Study 2 发现某段时间通过筛选的数量塌缩，回来这张表能查是不是因为
  当时 universe 本来就小，而不是筛选太严）。

运行前先设好连接环境变量（同 `research/worldquant_101/run_screening.py`）：
    CH_HOST=... CH_PASSWORD=... python research/tradability_calibration/run_distribution_study.py
"""

from __future__ import annotations

import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

from sherpa.metrics.tradability import DEFAULT_LOOKBACK

from data import END_TIME, INTERVAL, START_TIME, load_universe_panel

RESULTS_DIR = Path(__file__).parent / "results"
PERCENTILES = [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]


def rolling_distribution_summary(rolling: pd.DataFrame, label: str) -> pd.DataFrame:
    """把一个 (T,N) 滚动指标矩阵摊平成一维（丢掉 warm-up 阶段的 `NaN`），算分位数表。"""
    flat = pd.Series(rolling.to_numpy().ravel()).dropna()
    values = flat.quantile(PERCENTILES)
    return pd.DataFrame({"metric": label, "percentile": PERCENTILES, "value": values.to_numpy()})


def symbol_lifetime_summary(
    rolling_quote_volume: pd.DataFrame, rolling_trades_count: pd.DataFrame, close: pd.DataFrame
) -> pd.DataFrame:
    """每个 symbol 终身统计：有效 bar 数、第一次出现的时间、滚动成交额/成交笔数中位数。

    按 `median_rolling_quote_volume` 从低到高排——排在最前面的就是"终身成交额中位数最低"
    的那批，是判断"这是不是死币"最直接的肉眼核对依据。
    """
    rows = []
    for symbol in close.columns:
        valid = close[symbol].notna()
        rows.append({
            "symbol": symbol,
            "n_valid_bars": int(valid.sum()),
            "first_valid_time": close[symbol].first_valid_index(),
            "median_rolling_quote_volume": rolling_quote_volume[symbol].median(),
            "median_rolling_trades_count": rolling_trades_count[symbol].median(),
        })
    out = pd.DataFrame(rows)
    return out.sort_values("median_rolling_quote_volume", ascending=True, na_position="first")


def market_activity_over_time(panel) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "total_quote_volume": panel.quote_volume.sum(axis=1),
            "active_symbol_count": panel.close.notna().sum(axis=1),
        },
        index=panel.index,
    )


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    RESULTS_DIR.mkdir(exist_ok=True)

    rolling_quote_volume = panel.quote_volume.rolling(DEFAULT_LOOKBACK).median()
    rolling_trades_count = panel.trades_count.rolling(DEFAULT_LOOKBACK).median()

    print("\n== 分位数分布（跟 tradable_mask 同口径的滚动中位数）==")
    dist = pd.concat(
        [
            rolling_distribution_summary(rolling_quote_volume, "rolling_quote_volume"),
            rolling_distribution_summary(rolling_trades_count, "rolling_trades_count"),
        ],
        ignore_index=True,
    )
    dist.to_csv(RESULTS_DIR / "volume_distribution_summary.csv", index=False)
    print(dist.to_string(index=False))

    print("\n== 按 symbol 终身统计（成交额中位数最低的 15 个，死币候选）==")
    lifetime = symbol_lifetime_summary(rolling_quote_volume, rolling_trades_count, panel.close)
    lifetime.to_csv(RESULTS_DIR / "symbol_lifetime_summary.csv", index=False)
    print(lifetime.head(15).to_string(index=False))

    print("\n== 全市场活跃度随时间变化 ==")
    activity = market_activity_over_time(panel)
    activity.to_csv(RESULTS_DIR / "market_activity_over_time.csv")
    print(
        f"active_symbol_count 历史最小值: {activity['active_symbol_count'].min()}"
        f"（发生在 {activity['active_symbol_count'].idxmin()}）"
    )
    print(
        f"active_symbol_count 历史最大值: {activity['active_symbol_count'].max()}"
        f"（发生在 {activity['active_symbol_count'].idxmax()}）"
    )

    print(f"\n三张表已写入 {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
