"""逐期 RankIC 时间线（通用步骤）：参评因子在**整个研究段**（选择段 + 验证段）每根 bar 的 RankIC。

    CH_HOST=... CH_PASSWORD=... python research/alpha_research/_pipeline/run_ic_timeline.py <track_id 或研究线目录>

为什么要有这一步：RankIC 是横比模型的主判据（`MLalpha/RESULT_READING.md` §0、§5），但阶段一只看选择段、关卡3 的
`00` 只看验证段，都没有完整的逐期序列。ML 研究线的这份序列是训练步骤顺带产出的（`ml_training/<model>_ic_by_bar.csv`），
不训练的研究线（tradecraft 等）用这个脚本产出**同样格式**的三份文件，于是逐 fold 配对横比、`research/viz/` 的图都能
直接用，也能跟 ML 模型放在一起比。

口径（跟阶段一 / 关卡3 同一套处理链，跟 ML 的 `ic_by_bar.csv` 可比）：

- 分数：`sherpa.backtest.residual` 处理链（研究线的外层流动性掩码 + 中性化开关），跟阶段一同一个函数；
- 标签：从 `close[t + delay]` 持有到 `close[t + delay + horizon]` 的收益，套同一个掩码。`delay` 用
  `research_config.json` 的 `execution_delay_bars`；`horizon` 用因子自己声明的 `horizon_bars`（tradecraft alpha 的类属性），
  没声明就用 `research_config.json` 的 `horizon_bars`；
- 每期只用分数、标签都有值的币（等权 Spearman，`sherpa.metrics.factor.rank_ic`），少于 `MIN_PERIOD_SYMBOLS` 个币的期记 NaN
  （跟 ML 的 `min_period_rows` 一致）；
- 另外两列固定口径：`rank_ic_h1`（1 根，阶段一 / 关卡3 的口径）、`rank_ic_h6`（6 根，ML 模型主指标的口径），
  跟 ML 模型横比时用口径相同的那一列。

产出（`<run>/results*/ic_timeline/`，文件名前缀 = 因子的 `name`）：

- `<name>_ic_by_bar.csv`：每根 bar 一行——`rank_ic`（因子自己的持有期）、`rank_ic_h1`、`rank_ic_h6`、`n_symbols`、
  `fold_valid_from`（所属 20 天时段）、`segment`；
- `<name>_folds.csv`：每 20 天一段的 RankIC 均值 / IR / 为正比例。时段的划分跟 ML 的重训时间表对齐（研究起点 + 180 天
  起每 120 根一段，往前同样每 120 根一段铺到研究起点），同一个 `valid_from` 可以直接跟 ML 模型的 `folds.csv` 逐段配对；
- `<name>_oos_summary.csv`：按选择段 / 验证段 / 全部汇总；
- `<name>_ic_timeline.json`：这次用的口径（持有期、执行延迟、掩码、中性化）。

注意"样本外"的含义：规则型因子没有训练，选择段 / 验证段的区别只在**规则和参数是在哪段数据上定下来的**。规则定稿之前
看过验证段的结果，验证段就不再是样本外了。
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))

from sherpa.alpha import registry
from sherpa.backtest.residual import ScorePreprocessor, residual_score
from sherpa.data.schema import interval_to_timedelta
from sherpa.metrics.factor import forward_returns, rank_ic

from data import (
    BENCHMARK_SYMBOL,
    EXECUTION_DELAY_BARS,
    HORIZON_BARS,
    INTERVAL,
    RESEARCH_END,
    START_TIME,
    VALIDATION_START,
    load_universe_panel,
)
from track import load_track

STAGE = "ic_timeline"
REFERENCE_HORIZONS = (1, 6)  # 固定多算的两个口径：阶段一 / 关卡3 用 1 根，ML 主指标用 6 根
MIN_PERIOD_SYMBOLS = 20  # = research/ml_training/config.py 的 MIN_PERIOD_ROWS
# 20 天一段、锚点 = 研究起点 + 180 天：= research/ml_training/config.py 的 RETRAIN_EVERY_BARS / MIN_TRAIN_BARS（单测守住）
BLOCK_BARS = 6 * 20
ANCHOR_BARS = 6 * 180


def block_starts(times: pd.DatetimeIndex, *, research_start: pd.Timestamp, interval: str) -> pd.DatetimeIndex:
    """每个时点所属 20 天时段的起点。时段 = 锚点 + k × BLOCK_BARS 根（k 可以为负），跟 ML 的重训时点重合。"""
    bar = interval_to_timedelta(interval)
    anchor = research_start + ANCHOR_BARS * bar
    k = np.floor((times - anchor) / (BLOCK_BARS * bar)).astype(int)
    return pd.DatetimeIndex(anchor + k * (BLOCK_BARS * bar))


def ic_stats(ic: pd.Series) -> dict[str, float]:
    ic = ic.dropna()
    std = ic.std()
    return {
        "periods": int(len(ic)),
        "rank_ic_mean": float(ic.mean()) if len(ic) else float("nan"),
        "rank_ic_ir": float(ic.mean() / std) if len(ic) > 1 and std > 0 else float("nan"),
        "rank_ic_win_rate": float((ic > 0).mean()) if len(ic) else float("nan"),
    }


def _format_ts(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def timeline(score: pd.DataFrame, close: pd.DataFrame, preprocessor: ScorePreprocessor, *, horizon: int, delay: int,
             research_start: pd.Timestamp, validation_start: pd.Timestamp, interval: str) -> pd.DataFrame:
    """一个因子的逐期 RankIC 表（`ic_by_bar.csv` 的内容），从第一根有分数的 bar 开始。"""
    columns: dict[str, pd.Series] = {}
    counts = None
    for h in dict.fromkeys((horizon, *REFERENCE_HORIZONS)):
        labels = preprocessor.mask_labels(forward_returns(close, horizon=h, delay=delay))
        ic = rank_ic(score, labels)
        n = (score.notna() & labels.notna()).sum(axis=1).reindex(ic.index)
        ic[n < MIN_PERIOD_SYMBOLS] = np.nan
        columns[h] = ic
        if h == horizon:
            counts = n
    by_bar = pd.DataFrame({"rank_ic": columns[horizon]})
    for h in REFERENCE_HORIZONS:
        by_bar[f"rank_ic_h{h}"] = columns[h]
    by_bar["n_symbols"] = counts.astype(int)
    scored = score.notna().any(axis=1).reindex(by_bar.index, fill_value=False)
    by_bar = by_bar.loc[scored.idxmax():] if scored.any() else by_bar.iloc[0:0]
    by_bar = by_bar[by_bar["rank_ic"].notna() | (by_bar["n_symbols"] > 0)]
    by_bar["fold_valid_from"] = [_format_ts(t) for t in block_starts(by_bar.index, research_start=research_start, interval=interval)]
    by_bar["segment"] = np.where(by_bar.index < validation_start, "selection", "validation")
    by_bar.index.name = "time"
    return by_bar


def summaries(by_bar: pd.DataFrame, *, interval: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(每 20 天一段的 folds 表, 分段汇总)。"""
    bar = interval_to_timedelta(interval)
    folds = []
    for valid_from, rows in by_bar.groupby("fold_valid_from", sort=True):
        start = pd.Timestamp(valid_from)
        folds.append({"valid_from": valid_from, "valid_until": _format_ts(start + BLOCK_BARS * bar), **ic_stats(rows["rank_ic"])})
    summary = [
        {"segment": "selection(规则在这段定稿，偏乐观)", **ic_stats(by_bar.loc[by_bar["segment"] == "selection", "rank_ic"])},
        {"segment": "validation(规则定稿前没看过才算样本外)", **ic_stats(by_bar.loc[by_bar["segment"] == "validation", "rank_ic"])},
        {"segment": "all", **ic_stats(by_bar["rank_ic"])},
    ]
    return pd.DataFrame(folds), pd.DataFrame(summary)


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法：python run_ic_timeline.py <track_id 或研究线目录>")
    track = load_track(sys.argv[1])
    track.import_alpha_modules()
    names = track.select_alphas()
    print(f"研究线 {track.id} · 逐期 RankIC 时间线：{names}")
    print(f"  外层可流通性掩码：{track.tradable}；中性化：{track.neutralize}")

    print(f"\n正在从 ClickHouse 拉取整个研究段 {START_TIME} ~ {RESEARCH_END} 的 {INTERVAL} K 线（验证段从 {VALIDATION_START} 开始）……")
    panel = load_universe_panel(end_time=RESEARCH_END)
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 bar")
    preprocessor = ScorePreprocessor.from_panel(
        panel, benchmark_symbol=BENCHMARK_SYMBOL, tradable=track.tradable, neutralize=track.neutralize
    )
    research_start = pd.Timestamp(START_TIME, tz="UTC")
    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    out_dir = track.stage_results_dir(STAGE)
    out_dir.mkdir(parents=True, exist_ok=True)

    for qualified_name in names:
        started = time.monotonic()
        alpha = registry.get(qualified_name)()
        horizon = int(getattr(alpha, "horizon_bars", HORIZON_BARS))
        score = residual_score(alpha, panel, preprocessor)
        by_bar = timeline(score, panel.close, preprocessor, horizon=horizon, delay=EXECUTION_DELAY_BARS,
                          research_start=research_start, validation_start=validation_start, interval=INTERVAL)
        folds, summary = summaries(by_bar, interval=INTERVAL)
        prefix = type(alpha).name
        by_bar.to_csv(out_dir / f"{prefix}_ic_by_bar.csv")
        folds.to_csv(out_dir / f"{prefix}_folds.csv", index=False)
        summary.to_csv(out_dir / f"{prefix}_oos_summary.csv", index=False)
        (out_dir / f"{prefix}_ic_timeline.json").write_text(json.dumps({
            "alpha": qualified_name,
            "horizon_bars": horizon,
            "execution_delay_bars": EXECUTION_DELAY_BARS,
            "reference_horizons": list(REFERENCE_HORIZONS),
            "tradable_mask": track.tradable,
            "neutralize": track.neutralize,
            "min_period_symbols": MIN_PERIOD_SYMBOLS,
            "research_start": START_TIME,
            "validation_start": VALIDATION_START,
            "research_end": RESEARCH_END,
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n== {qualified_name}（持有 {horizon} 根、执行延迟 {EXECUTION_DELAY_BARS} 根），用时 {time.monotonic() - started:.0f} 秒 ==")
        print(summary.round(4).to_string(index=False))
        print(f"  参考口径 1 根 / 6 根的全段均值：{by_bar['rank_ic_h1'].mean():.4f} / {by_bar['rank_ic_h6'].mean():.4f}")
        print(f"  -> {out_dir / f'{prefix}_ic_by_bar.csv'}、_folds.csv、_oos_summary.csv、_ic_timeline.json")


if __name__ == "__main__":
    main()
