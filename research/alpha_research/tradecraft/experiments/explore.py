"""tradecraft 探索实验：一批参数组合（实例）用跟正式研究线同一套口径快速评估，挑出值得进正式研究线的。

    python research/alpha_research/tradecraft/experiments/explore.py --batch b1_decompose
    python research/alpha_research/tradecraft/experiments/explore.py --batch b1_decompose --only full,accel_only

每个实例 = 某个 tradecraft 基类（比如 `LiquiditySurgeBase`）的一组类属性，脚本现场生成子类再 `compute(panel)`——跟正式
实例是同一份代码，探索选出来的参数原样写成注册的子类即可，打分逐格相同。

评估口径（跟正式研究线一致，可以直接跟 V4 等模型横比）：

- **数据**：MLalpha 探索的面板缓存（`research_start ~ research_end`，跟研究线取数同一个 universe 口径），没有缓存时从
  ClickHouse 取一次（要 CH_HOST / CH_PASSWORD）；
- **RankIC**：`sherpa.metrics.factor.rank_ic`，标签 = 从 `close[t+1]` 持有到 `close[t+1+h]`（执行延迟 1 根），套研究线掩码，
  h = 1（默认持有期）和 6（ML 主指标口径）。这是步骤 0（`run_ic_timeline.py`）的同一套计算；
- **扣费回测**：`research/ml_training/evaluation.py`（关卡3 的网格、成本、稳健性过滤，单测保证跟 `friction_test/config.py`
  一致）对 39 个组合各跑一次，分段从第一根有打分的 bar 开始（同关卡3）；
- **分段**：选择段挑、验证段确认。择时会让一部分 bar 空仓，所以另外报"有打分的 bar 占比"和空仓比例；关卡3 的 04 表会把
  选择段空仓 > 20% 的组合剔掉，这里同时给出剔除前后的中位数。

产出：`experiments/<batch>/summary.csv`（每个实例一行）、`ic.csv`（每个实例的逐期 RankIC，1 根）、`grid.csv`（每个实例 ×
39 组合 × 成本 × 段的长表）。结论写进 `experiments/FINDINGS.md`。
"""

from __future__ import annotations

import argparse
import json
import os
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
EXPERIMENTS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "research" / "ml_training"))  # evaluation.py：关卡3 同口径的扣费回测

import evaluation  # noqa: E402

from sherpa.alpha.custom.tradecraft import TRADECRAFT_LIQUIDITY  # noqa: E402
from sherpa.alpha.custom.tradecraft import indicators  # noqa: E402
from sherpa.alpha.custom.tradecraft.liquidity_surge import LiquiditySurgeBase  # noqa: E402
from sherpa.metrics.factor import forward_returns, rank_ic  # noqa: E402

CONFIG = json.loads((ROOT / "research" / "research_config.json").read_text(encoding="utf-8"))
VALIDATION_START = pd.Timestamp(CONFIG["window"]["validation_start"], tz="UTC")
DELAY = int(CONFIG["label"]["execution_delay_bars"])
CACHE = ROOT / "research" / "alpha_research" / "MLalpha" / "experiments" / "_cache" / (
    f"panel_{CONFIG['window']['research_start']}_{CONFIG['window']['research_end']}.pkl")
HORIZONS = (1, 6)
MIN_PERIOD_SYMBOLS = 20  # 同 run_ic_timeline.py
PERIODS_PER_YEAR = 365 * 6
WORKERS = int(os.environ.get("SHERPA_MAX_WORKERS", 16))

# ---------------------------------------------------------------------------------------------
# 实例：batch -> {名字: (基类, 类属性, 说明)}
# ---------------------------------------------------------------------------------------------
LS = LiquiditySurgeBase
OFF = {"w_accel": 0.0, "w_breakout": 0.0, "w_shadow": 0.0}
BATCHES: dict[str, dict[str, tuple[type, dict[str, Any], str]]] = {
    # 第一批：把三项拆开看各自的方向和强弱，看候选池本身有没有用
    "b1_decompose": {
        "full": (LS, {}, "默认：池 30%，三项等权"),
        "accel_only": (LS, {**OFF, "w_accel": 1.0}, "只用涨幅变化率（加速的分高）"),
        "breakout_only": (LS, {**OFF, "w_breakout": 1.0}, "只用已经涨了多少（涨得少的分高）"),
        "shadow_only": (LS, {**OFF, "w_shadow": 1.0}, "只用上影线（上影线短的分高）"),
        "full_nopool": (LS, {"pool_quantile": 1.0}, "三项等权，不设候选池（范围内全部币）"),
        "accel_nopool": (LS, {**OFF, "w_accel": 1.0, "pool_quantile": 1.0}, "只用变化率，不设候选池"),
        "breakout_nopool": (LS, {**OFF, "w_breakout": 1.0, "pool_quantile": 1.0}, "只用涨幅，不设候选池"),
        "shadow_nopool": (LS, {**OFF, "w_shadow": 1.0, "pool_quantile": 1.0}, "只用上影线，不设候选池"),
    },
    # 第二批：第一批里"涨得少"最强、上影线有一点、变化率（加速度）没有信号；成本吃光收益（换手 0.3～0.6 / 根）。
    # 以"涨得少 + 上影线短"（bs）为核心，试：池子大小、放量窗口拉长（池子成员更稳 → 换手低）、"突破"换成区间位置、
    # 以及"涨幅变化率平缓"这种理解（|变化率| 越小分越高）
    "b2_refine": {
        "bs": (LS, {"w_accel": 0.0}, "涨得少 + 上影线短，池 30%"),
        "bs_p50": (LS, {"w_accel": 0.0, "pool_quantile": 0.5}, "同上，池 50%"),
        "bs_s12": (LS, {"w_accel": 0.0, "surge_short": 12}, "放量用最近 2 天 vs 7 天"),
        "bs_s18_l120": (LS, {"w_accel": 0.0, "surge_short": 18, "surge_long": 120}, "放量用最近 3 天 vs 20 天"),
        "bs_ret18": (LS, {"w_accel": 0.0, "breakout_bars": 18}, "涨幅看最近 3 天"),
        "bs_range42": (LS, {"w_accel": 0.0, "breakout_kind": "range", "breakout_bars": 42}, "突破 = 7 天区间位置（越靠底分越高）"),
        "bs_range42_p50_s12": (LS, {"w_accel": 0.0, "breakout_kind": "range", "breakout_bars": 42, "pool_quantile": 0.5,
                                    "surge_short": 12}, "区间位置 + 池 50% + 放量 2 天"),
        "flat_full": (LS, {"accel_kind": "flat"}, "三项：变化率平缓 + 涨得少 + 上影线短（按原话）"),
        "flat_only": (LS, {**OFF, "w_accel": 1.0, "accel_kind": "flat"}, "只用变化率平缓"),
        "flat_full_range42": (LS, {"accel_kind": "flat", "breakout_kind": "range", "breakout_bars": 42},
                              "变化率平缓 + 区间位置低 + 上影线短"),
    },
    # 第三批：flat_full（按原话的三项）RankIC 最好，但收益被空头腿拖累——打最低分的"已经冲高"的币右尾极肥，做空被轧。
    # 试：① 池内涨幅最大的一部分直接不参与；② 原则 3 的横盘择时（大盘趋势效率低于过去的某个分位时整期不交易）
    "b3_tail_gate": {
        "ff": (LS, {"accel_kind": "flat"}, "flat_full 原样"),
        "ff_x10": (LS, {"accel_kind": "flat", "exclude_top_breakout": 0.1}, "池内涨幅前 10% 不参与"),
        "ff_x20": (LS, {"accel_kind": "flat", "exclude_top_breakout": 0.2}, "池内涨幅前 20% 不参与"),
        "ff_x30": (LS, {"accel_kind": "flat", "exclude_top_breakout": 0.3}, "池内涨幅前 30% 不参与"),
        "ff_p50_x20": (LS, {"accel_kind": "flat", "pool_quantile": 0.5, "exclude_top_breakout": 0.2}, "池 50%，涨幅前 20% 不参与"),
        "ff_g20": (LS, {"accel_kind": "flat", "gate_quantile": 0.2}, "BTC 7 天趋势效率低于过去 180 天 20% 分位时不交易"),
        "ff_g33": (LS, {"accel_kind": "flat", "gate_quantile": 0.33}, "同上，33% 分位"),
        "ff_g50": (LS, {"accel_kind": "flat", "gate_quantile": 0.5}, "同上，50% 分位"),
        "ff_g33_er18": (LS, {"accel_kind": "flat", "gate_quantile": 0.33, "gate_bars": 18}, "趋势效率看 3 天，33% 分位"),
        "ff_x20_g33": (LS, {"accel_kind": "flat", "exclude_top_breakout": 0.2, "gate_quantile": 0.33}, "涨幅前 20% 不参与 + 择时 33%"),
    },
    # 第四批：排除暴涨币、横盘择时都没改善排序；卡脖子的是换手（0.3 / 根，V4 的两倍，保本成本只有 2～4 bps）。
    # 三项都只看最近 3～6 根、候选池成员变得快；而 6 根 RankIC（0.06）明显强于 1 根，信号能持续一天左右——把窗口整体拉长
    "b4_slow": {
        "ff": (LS, {"accel_kind": "flat"}, "flat_full 原样（3 / 6 / 3 根，放量 1 天 vs 7 天）"),
        "ff_a6": (LS, {"accel_kind": "flat", "accel_bars": 6}, "变化率看 1 天 vs 前 1 天"),
        "ff_a6_sh6": (LS, {"accel_kind": "flat", "accel_bars": 6, "shadow_bars": 6}, "变化率、上影线都看 1 天"),
        "ff_a6_sh6_b12": (LS, {"accel_kind": "flat", "accel_bars": 6, "shadow_bars": 6, "breakout_bars": 12},
                          "再加：涨幅看 2 天"),
        "ff_slow": (LS, {"accel_kind": "flat", "accel_bars": 6, "shadow_bars": 6, "breakout_bars": 12, "surge_short": 12},
                    "全部拉长：变化率 / 上影线 1 天、涨幅 2 天、放量 2 天 vs 7 天"),
        "ff_slow_p50": (LS, {"accel_kind": "flat", "accel_bars": 6, "shadow_bars": 6, "breakout_bars": 12, "surge_short": 12,
                             "pool_quantile": 0.5}, "全部拉长 + 池 50%"),
        "ff_slower": (LS, {"accel_kind": "flat", "accel_bars": 12, "shadow_bars": 12, "breakout_bars": 18, "surge_short": 18,
                           "surge_long": 120}, "更慢：变化率 / 上影线 2 天、涨幅 3 天、放量 3 天 vs 20 天"),
    },
}


def make_alpha(base: type, params: dict[str, Any], name: str):
    cls = type(f"Explore_{name}", (base,), {"name": f"tc_x_{name}", **params})
    return cls()


# ---------------------------------------------------------------------------------------------
# 扣费回测（多进程，每个实例一个任务，39 个组合在一个进程里跑完）
# ---------------------------------------------------------------------------------------------
_close: pd.DataFrame | None = None
_interval: str = "4h"


def _init(close: pd.DataFrame, interval: str) -> None:
    global _close, _interval
    _close, _interval = close, interval


def _grid(name: str, ranked: pd.DataFrame) -> list[dict[str, Any]]:
    scored = ranked.notna().any(axis=1)
    start = scored.idxmax()
    index = ranked.index
    segments = {
        "selection": pd.Series((index >= start) & (index < VALIDATION_START), index=index),
        "validation": pd.Series(index >= VALIDATION_START, index=index),
    }
    rows = []
    for weighting, spec in evaluation.WEIGHTINGS.items():
        for rebalance in evaluation.REBALANCE_EVERY:
            for row in evaluation.backtest(ranked, _close, _interval, spec=spec, rebalance_every=rebalance, shift=1 + DELAY,
                                           segments=segments, periods_per_year=PERIODS_PER_YEAR):
                rows.append({"variant": name, "weighting": weighting, "rebalance_every": rebalance, **row})
    return rows


def robustness(grid: pd.DataFrame) -> dict[str, float]:
    """04 表口径：吃单两段中位数 / 两段都为正占比（剔除选择段空仓 > 20% 的组合），另给不剔除的中位数和平均空仓比例。"""
    out: dict[str, float] = {}
    keys = ["weighting", "rebalance_every"]
    sel_flat = grid[(grid.cost_model == "zero") & (grid.segment == "selection")].set_index(keys)["flat_bar_fraction"]
    usable = sel_flat[sel_flat <= evaluation.ROBUSTNESS_MAX_FLAT].index
    out["flat_sel"] = float(sel_flat.mean())
    out["combos_kept"] = int(len(usable))
    for cost in ("all_taker", "all_maker", "zero"):
        g = grid[grid.cost_model == cost]
        wide = g.set_index(keys).pivot(columns="segment", values="net_sharpe")
        tag = {"all_taker": "taker", "all_maker": "maker", "zero": "gross"}[cost]
        out[f"{tag}_sel_all"] = float(wide["selection"].median())
        out[f"{tag}_val_all"] = float(wide["validation"].median())
        kept = wide.loc[wide.index.intersection(usable)]
        out[f"{tag}_sel"] = float(kept["selection"].median()) if len(kept) else float("nan")
        out[f"{tag}_val"] = float(kept["validation"].median()) if len(kept) else float("nan")
        if cost == "all_taker":
            out["taker_both_pos"] = float(((kept["selection"] > 0) & (kept["validation"] > 0)).mean()) if len(kept) else float("nan")
            out["taker_both_pos_all"] = float(((wide["selection"] > 0) & (wide["validation"] > 0)).mean())
    return out


def ic_stats(ic: pd.Series, prefix: str) -> dict[str, float]:
    out = {}
    for seg, mask in (("sel", ic.index < VALIDATION_START), ("val", ic.index >= VALIDATION_START)):
        x = ic[mask].dropna()
        out[f"{prefix}_{seg}"] = float(x.mean()) if len(x) else float("nan")
        out[f"{prefix}_{seg}_ir"] = float(x.mean() / x.std()) if len(x) > 1 and x.std() > 0 else float("nan")
    return out


def load_panel():
    if CACHE.exists():
        return pickle.loads(CACHE.read_bytes())
    sys.path.insert(0, str(ROOT / "research" / "alpha_research" / "_pipeline"))
    from data import RESEARCH_END, load_universe_panel  # noqa: E402

    panel = load_universe_panel(end_time=RESEARCH_END)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_bytes(pickle.dumps(panel))
    return panel


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="tradecraft 探索实验")
    parser.add_argument("--batch", required=True, choices=sorted(BATCHES))
    parser.add_argument("--only", default=None, help="只跑这几个实例（逗号分隔）")
    parser.add_argument("--no-grid", action="store_true", help="只算 RankIC，不跑扣费回测")
    args = parser.parse_args(argv)

    variants = BATCHES[args.batch]
    if args.only:
        variants = {k: v for k, v in variants.items() if k in set(args.only.split(","))}
    out_dir = EXPERIMENTS / args.batch
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    panel = load_panel()
    scope = TRADECRAFT_LIQUIDITY.mask(panel)
    labels = {h: forward_returns(panel.close, horizon=h, delay=DELAY).where(scope) for h in HORIZONS}
    print(f"面板 {panel.close.shape}，{panel.close.index[0]} ~ {panel.close.index[-1]}；范围内平均每期 {scope.sum(axis=1).mean():.0f} 个币"
          f"（{time.monotonic() - started:.0f} 秒）", flush=True)

    rows: dict[str, dict[str, Any]] = {}
    ics: dict[str, pd.Series] = {}
    ranked_by_variant: dict[str, pd.DataFrame] = {}
    for name, (base, params, note) in variants.items():
        alpha = make_alpha(base, params, name)
        score = alpha.compute(panel)
        row: dict[str, Any] = {"variant": name, "note": note, "params": json.dumps(params, ensure_ascii=False)}
        n = score.notna().sum(axis=1)
        live = n >= MIN_PERIOD_SYMBOLS
        first = live.idxmax()
        row["active_frac"] = float(live.loc[first:].mean())
        row["symbols_per_bar"] = float(n[live].mean())
        for h in HORIZONS:
            ic = rank_ic(score, labels[h])
            ic[~live.reindex(ic.index, fill_value=False)] = np.nan
            row.update(ic_stats(ic, f"ic{h}"))
            if h == 1:
                ics[name] = ic
        rows[name] = row
        ranked_by_variant[name] = evaluation.cross_sectional_rank(score)
        print(f"  {name:<20} IC1 选 / 验 {row['ic1_sel']:+.4f} / {row['ic1_val']:+.4f}   IC6 {row['ic6_sel']:+.4f} / {row['ic6_val']:+.4f}"
              f"   有打分 {row['active_frac']:.0%}，每期 {row['symbols_per_bar']:.0f} 个币", flush=True)

    if not args.no_grid:
        print(f"\n扣费回测：{len(variants)} 个实例 × {len(evaluation.WEIGHTINGS) * len(evaluation.REBALANCE_EVERY)} 个组合，"
              f"{min(WORKERS, len(variants))} 个进程……", flush=True)
        grid_rows: list[dict[str, Any]] = []
        with ProcessPoolExecutor(max_workers=min(WORKERS, len(variants)), initializer=_init,
                                 initargs=(panel.close, panel.interval)) as pool:
            futures = {pool.submit(_grid, name, ranked): name for name, ranked in ranked_by_variant.items()}
            for done, future in enumerate(as_completed(futures), 1):
                name = futures[future]
                part = pd.DataFrame(future.result())
                grid_rows += part.to_dict("records")
                rows[name].update(robustness(part))
                r = rows[name]
                print(f"  [{done}/{len(futures)}] {name:<20} 吃单 选 / 验 {r['taker_sel']:+.2f} / {r['taker_val']:+.2f}"
                      f"（两段都正 {r['taker_both_pos']:.0%}，保留 {r['combos_kept']} 组合，选择段平均空仓 {r['flat_sel']:.0%}）"
                      f"  不剔除 {r['taker_sel_all']:+.2f} / {r['taker_val_all']:+.2f}", flush=True)
        pd.DataFrame(grid_rows).to_csv(out_dir / "grid.csv", index=False)

    summary = pd.DataFrame(rows.values())
    summary.to_csv(out_dir / "summary.csv", index=False)
    pd.DataFrame(ics).to_csv(out_dir / "ic.csv")
    print(f"\n-> {out_dir}（用时 {(time.monotonic() - started) / 60:.1f} 分钟）")


if __name__ == "__main__":
    main()
