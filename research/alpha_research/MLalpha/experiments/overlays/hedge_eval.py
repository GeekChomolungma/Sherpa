"""BTC beta 对冲 ± 趋势开关，在全部 39 个组合上比较。

对冲：每个调仓行，组合净 beta β_p = Σ w_i · β_i（β_i = 各币对 BTC 的滚动 beta，point-in-time），在 BTC 上加 −β_p 的仓位
（直接加进目标权重，漂移 / 换手 / 手续费照常由回测器算）。开关同 gate_eval.py（门槛取选择段分位数）。

用法：python hedge_eval.py <scores.pkl> <out_dir> [beta_window]
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
from sherpa.risk.exposure import rolling_beta

COST = 8e-4
PPY = 6 * 365
_W = {}


def _init(close, targets, beta, gates, segments):
    _W.update(close=close, targets=targets, beta=beta, gates=gates, segments=segments)


def _run(args):
    combo, variant = args
    weighting, rebalance = combo
    hedge, gate_name = variant.split("+") if "+" in variant else (variant, "none")
    w = _W["targets"][combo]
    g = _W["gates"][gate_name].reindex(w.index).fillna(1.0)
    w = w.mul(g, axis=0)
    if hedge == "hedge":
        beta_p = (w * _W["beta"].reindex_like(w)).sum(axis=1)
        w = w.copy()
        w["BTCUSDT"] = w["BTCUSDT"] - beta_p.where(w.abs().sum(axis=1) > 0, 0.0)
    gross, turnover = run_score_backtest(w, _W["close"], "4h", shift=2, rebalance_every=rebalance)
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


def main():
    scores_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    beta_window = int(sys.argv[3]) if len(sys.argv) > 3 else None
    out.mkdir(parents=True, exist_ok=True)
    panel = pickle.loads((ROOT / "research/alpha_research/MLalpha/experiments/_cache/panel_2023-01-01_2026-03-15.pkl").read_bytes())
    scope = LgbmV4.spec.liquidity.mask(panel)
    ranked = cross_sectional_rank(pd.read_pickle(scores_path).reindex(index=panel.close.index, columns=panel.close.columns).where(scope))
    start = ranked.notna().any(axis=1).idxmax()
    vstart = pd.Timestamp(VALIDATION_START, tz="UTC")
    idx = panel.close.index
    segments = {"selection": pd.Series((idx >= start) & (idx < vstart), index=idx),
                "validation": pd.Series(idx >= vstart, index=idx)}
    kw = {} if beta_window is None else {"window": beta_window}
    beta = rolling_beta(panel.close, benchmark_symbol="BTCUSDT", **kw).fillna(1.0)

    sig = gate_signals(panel)
    sel = segments["selection"]
    gates = {"none": pd.Series(1.0, index=idx),
             "abs_btc_42_soft": make_gate(sig["abs_btc_42"], sel, "soft", 0.6),
             "trend_t_120_soft": make_gate(sig["trend_t_120"], sel, "soft", 0.6),
             "abs_mkt_42_soft": make_gate(sig["abs_mkt_42"], sel, "soft", 0.6)}
    variants = ["raw", "hedge"] + [f"{h}+{g}" for h in ("raw", "hedge") for g in gates if g != "none"]

    combos = [(w, r) for w in evaluation.WEIGHTINGS for r in evaluation.REBALANCE_EVERY]
    targets = {c: target_path(ranked, evaluation.WEIGHTINGS[c[0]], c[1]) for c in combos}
    jobs = [(c, v) for c in combos for v in variants]
    with ProcessPoolExecutor(max_workers=4, initializer=_init, initargs=(panel.close, targets, beta, gates, segments)) as pool:
        rows = [row for rs in pool.map(_run, jobs, chunksize=4) for row in rs]
    df = pd.DataFrame(rows)
    df.to_csv(out / "hedge_grid.csv", index=False)
    med = df.groupby(["variant", "segment"])[["sharpe", "mdd", "calmar", "ann_ret", "turnover"]].median().unstack("segment")
    wide = df.pivot_table(index=["variant", "weighting", "rebalance_every"], columns="segment", values="sharpe")
    med[("both_pos", "")] = ((wide["selection"] > 0) & (wide["validation"] > 0)).groupby("variant").mean()
    med.columns = ["|".join(c).strip("|") for c in med.columns]
    pd.set_option("display.width", 250)
    print(med.round(3).to_string())


if __name__ == "__main__":
    main()
