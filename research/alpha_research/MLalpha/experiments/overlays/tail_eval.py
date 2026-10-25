"""币层面的"不参与"：不做空截面上最难控制的币（近 42 根波动最高的那一档），± 趋势开关，全部 39 个组合。

做法：在流动性范围内按 vol_42 截面排名，排在前 (1 − p) 的币如果打分在下半边（会被选进空头），把打分抬到 0（截面中位数），
它们就不会进空头腿，空头名额由打分次低的币补上；做多不受影响。`both` 版本则两边都不碰（打分置 NaN）。
所有量只用 t 时刻已知的数据。

用法：python tail_eval.py <scores.pkl> <out_dir>
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
from gate_eval import _mdd, _sharpe, gate_signals, make_gate
from sherpa.alpha.custom.ml.models import LgbmV4
from sherpa.backtest.score_backtest import cross_sectional_rank, run_score_backtest, target_path

COST = 8e-4
PPY = 6 * 365
_W = {}


def _init(close, rankings, gates, segments):
    _W.update(close=close, rankings=rankings, gates=gates, segments=segments)


def _run(args):
    combo, variant = args
    weighting, rebalance = combo
    rank_name, gate_name = variant.split("+") if "+" in variant else (variant, "none")
    w = target_path(_W["rankings"][rank_name], evaluation.WEIGHTINGS[weighting], rebalance)
    g = _W["gates"][gate_name].reindex(w.index).fillna(1.0)
    gross, turnover = run_score_backtest(w.mul(g, axis=0), _W["close"], "4h", shift=2, rebalance_every=rebalance)
    net = gross - turnover * COST
    rows = []
    for seg, mask in _W["segments"].items():
        r = net[mask.reindex(net.index, fill_value=False)]
        m = _mdd(r)
        rows.append({"weighting": weighting, "rebalance_every": rebalance, "variant": variant, "segment": seg,
                     "sharpe": _sharpe(r), "mdd": m, "ann_ret": r.mean() * PPY,
                     "calmar": r.mean() * PPY / abs(m) if m < 0 else np.nan,
                     "turnover": float(turnover.reindex(r.index).mean())})
    return rows


def summarize(df: pd.DataFrame) -> pd.DataFrame:
    med = df.groupby(["variant", "segment"])[["sharpe", "mdd", "calmar", "ann_ret", "turnover"]].median().unstack("segment")
    wide = df.pivot_table(index=["variant", "weighting", "rebalance_every"], columns="segment", values="sharpe")
    med[("both_pos", "")] = ((wide["selection"] > 0) & (wide["validation"] > 0)).groupby("variant").mean()
    med.columns = ["|".join(c).strip("|") for c in med.columns]
    return med


def main():
    scores_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    panel = pickle.loads((ROOT / "research/alpha_research/MLalpha/experiments/_cache/panel_2023-01-01_2026-03-15.pkl").read_bytes())
    scope = LgbmV4.spec.liquidity.mask(panel)
    ranked = cross_sectional_rank(pd.read_pickle(scores_path).reindex(index=panel.close.index, columns=panel.close.columns).where(scope))
    start = ranked.notna().any(axis=1).idxmax()
    vstart = pd.Timestamp(VALIDATION_START, tz="UTC")
    idx = panel.close.index
    segments = {"selection": pd.Series((idx >= start) & (idx < vstart), index=idx),
                "validation": pd.Series(idx >= vstart, index=idx)}

    vol_rank = panel.close.pct_change(fill_method=None).rolling(42).std().where(ranked.notna()).rank(axis=1, pct=True)
    rankings = {"raw": ranked}
    for p in (0.9, 0.8):
        hot = vol_rank > p
        rankings[f"noshort_vol{int(p * 100)}"] = ranked.mask(hot & (ranked < 0), 0.0)
        rankings[f"skip_vol{int(p * 100)}"] = cross_sectional_rank(ranked.mask(hot))

    sig = gate_signals(panel)
    gates = {"none": pd.Series(1.0, index=idx),
             "abs_btc_42_soft": make_gate(sig["abs_btc_42"], segments["selection"], "soft", 0.6)}
    variants = list(rankings) + [f"{r}+abs_btc_42_soft" for r in rankings]
    combos = [(w, r) for w in evaluation.WEIGHTINGS for r in evaluation.REBALANCE_EVERY]
    jobs = [(c, v) for c in combos for v in variants]
    with ProcessPoolExecutor(max_workers=4, initializer=_init, initargs=(panel.close, rankings, gates, segments)) as pool:
        rows = [row for rs in pool.map(_run, jobs, chunksize=4) for row in rs]
    df = pd.DataFrame(rows)
    df.to_csv(out / "tail_grid.csv", index=False)
    pd.set_option("display.width", 250)
    print(summarize(df).round(3).to_string())


if __name__ == "__main__":
    main()
