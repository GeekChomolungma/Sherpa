"""两种架构（树模型 / LSTM）的打分：等权合成，以及"意见一致才下注"的三种做法，全部 39 个组合。

- `blend`：两张打分各自截面排名后取平均（不同后端的原始输出量级不同，不能直接平均）；
- `agree_gate`：组合层面的开关。t 时刻两张打分的截面秩相关 ρ_t（只用 t 时刻的打分，point-in-time）低于选择段的 q 分位时减仓
  （软开关，同 gate_eval 的口径：低于 q 分位开始线性降，到 5% 分位降到 0）；
- `agree_coin`：币层面。合成打分里，两个模型方向相反（一个在上半边、一个在下半边）的币打分置 NaN，不参与选币；
- `agree_both`：上面两个一起。

用法：python agree_eval.py <out_dir> <scoresA.pkl> <scoresB.pkl>
"""
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

SP = Path(__file__).resolve().parent
ROOT = Path(r"D:/code-repo/Chomo/Sherpa")
sys.path.insert(0, str(ROOT / "research" / "ml_training"))
sys.path.insert(0, str(SP))

import numpy as np
import pandas as pd

import evaluation
from data import VALIDATION_START
from sherpa.alpha.custom.ml.models import LgbmV4
from sherpa.backtest.score_backtest import cross_sectional_rank
from tail_eval import _init, _run, summarize


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    panel = pickle.loads((ROOT / "research/alpha_research/MLalpha/experiments/_cache/panel_2023-01-01_2026-03-15.pkl").read_bytes())
    scope = LgbmV4.spec.liquidity.mask(panel)
    ra, rb = (cross_sectional_rank(pd.read_pickle(p).reindex(index=panel.close.index, columns=panel.close.columns).where(scope))
              for p in sys.argv[2:4])
    both = ra.notna() & rb.notna()
    ra, rb = ra.where(both), rb.where(both)
    blend = cross_sectional_rank((ra + rb) / 2)
    start = blend.notna().any(axis=1).idxmax()
    vstart = pd.Timestamp(VALIDATION_START, tz="UTC")
    idx = panel.close.index
    segments = {"selection": pd.Series((idx >= start) & (idx < vstart), index=idx),
                "validation": pd.Series(idx >= vstart, index=idx)}

    rho = ra.corrwith(rb, axis=1)  # 同一时刻两张截面排名的相关（排名的 Pearson = Spearman）
    sel = segments["selection"] & rho.notna()
    gates = {"none": pd.Series(1.0, index=idx)}
    for q in (0.2, 0.4):
        lo, floor = rho[sel].quantile(q), rho[sel].quantile(0.05)
        gates[f"agree_q{int(q * 100)}"] = ((rho - floor) / (lo - floor)).clip(0, 1).where(rho.notna(), 1.0)
    disagree = (ra * rb) < 0
    rankings = {"a": ra, "b": rb, "blend": blend, "agree_coin": cross_sectional_rank(blend.mask(disagree))}
    variants = ["a", "b", "blend", "agree_coin"] + ([f"{r}+{g}" for r in ("blend", "agree_coin") for g in gates if g != "none"] if len(sys.argv) <= 4 else [])

    print(f"两张打分的截面秩相关 ρ：选择段中位数 {rho[segments['selection']].median():.2f}，验证段 {rho[segments['validation']].median():.2f}；"
          f"方向相反的币占比 {disagree[both].mean().mean():.0%}", flush=True)
    combos = [(w, r) for w in evaluation.WEIGHTINGS for r in evaluation.REBALANCE_EVERY]
    jobs = [(c, v) for c in combos for v in variants]
    with ProcessPoolExecutor(max_workers=4, initializer=_init, initargs=(panel.close, rankings, gates, segments)) as pool:
        rows = [row for rs in pool.map(_run, jobs, chunksize=4) for row in rs]
    df = pd.DataFrame(rows)
    df.to_csv(out / "agree_grid.csv", index=False)
    rho.to_pickle(out / "rho.pkl")
    for name in ("blend", "agree_coin"):
        rankings[name].to_pickle(out / f"{name}.pkl")
    pd.set_option("display.width", 250)
    print(summarize(df).round(3).to_string())


if __name__ == "__main__":
    main()
