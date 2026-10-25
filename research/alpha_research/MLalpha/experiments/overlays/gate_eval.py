"""在打分之上加一层"不确定就不参与"的仓位开关，在全部 39 个组合（关卡3 同一套映射 × 调仓频率）上比较加开关前后的效果。

开关 g_t ∈ [0, 1] 只在调仓行生效：目标权重 × g_t（g = 0 就是空仓，平仓 / 重新建仓的换手照常扣费）。持仓路径本身
（Top-K + 迟滞的状态）不受开关影响，开关只决定"这一期押多少"。所有开关信号只用 t 时刻已知的数据。

门槛只在**选择段**上定（信号在选择段上的分位数），验证段只用来确认。

用法：python gate_eval.py <scores.pkl> <out_dir>
"""
import pickle
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(r"D:/code-repo/Chomo/Sherpa")
sys.path.insert(0, str(ROOT / "research" / "ml_training"))

import numpy as np
import pandas as pd

import evaluation
from data import VALIDATION_START
from sherpa.alpha.custom.ml.models import LgbmV4
from sherpa.backtest.score_backtest import cross_sectional_rank, run_score_backtest, target_path

COST = 8e-4
PPY = 6 * 365
_W = {}


def gate_signals(panel) -> pd.DataFrame:
    """候选的"行情不清晰"度量（越大越不清晰），全部 point-in-time。"""
    btc = panel.close["BTCUSDT"]
    r = btc.pct_change(fill_method=None)
    vol = r.rolling(120, min_periods=60).std()
    out = {}
    for w in (6, 18, 42, 120):
        move = btc.pct_change(w, fill_method=None)
        out[f"abs_btc_{w}"] = move.abs()
        out[f"trend_t_{w}"] = (move / (vol * np.sqrt(w))).abs()  # 趋势强度按自身波动标准化
    # 全市场等权（山寨整体）的单边程度：截面平均收益的近 42 根累计
    mkt = panel.close.pct_change(fill_method=None).mean(axis=1)
    out["abs_mkt_42"] = mkt.rolling(42).sum().abs()
    return pd.DataFrame(out)


def make_gate(x: pd.Series, sel: pd.Series, kind: str, q: float) -> pd.Series:
    """`hard`：信号超过选择段 q 分位就空仓；`soft`：在选择段 q 分位到 0.95 分位之间线性降到 0。"""
    lo = x[sel].quantile(q)
    if kind == "hard":
        g = (x <= lo).astype(float)
    else:
        hi = x[sel].quantile(0.95)
        g = (1 - (x - lo) / (hi - lo)).clip(0, 1)
    return g.where(x.notna(), 1.0)  # 信号 warm-up 期不干预


def _init(close, targets, gates, segments):
    _W.update(close=close, targets=targets, gates=gates, segments=segments)


def _sharpe(r):
    return r.mean() / r.std() * np.sqrt(PPY) if len(r) > 1 and r.std() > 0 else np.nan


def _mdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def _run(args):
    combo, gate_name = args
    weighting, rebalance = combo
    targets = _W["targets"][combo]
    g = _W["gates"][gate_name].reindex(targets.index).fillna(1.0)
    gross, turnover = run_score_backtest(targets.mul(g, axis=0), _W["close"], "4h", shift=2, rebalance_every=rebalance)
    net = gross - turnover * COST
    rows = []
    for seg, mask in _W["segments"].items():
        r = net[mask.reindex(net.index, fill_value=False)]
        exposure = g.reindex(r.index)
        rows.append({"weighting": weighting, "rebalance_every": rebalance, "gate": gate_name, "segment": seg,
                     "sharpe": _sharpe(r), "mdd": _mdd(r), "ann_ret": r.mean() * PPY,
                     "calmar": r.mean() * PPY / abs(_mdd(r)) if _mdd(r) < 0 else np.nan,
                     "in_market": float((exposure > 0).mean()), "avg_exposure": float(exposure.mean()),
                     "turnover": float(turnover.reindex(r.index).mean())})
    return rows


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

    sig = gate_signals(panel)
    sel = segments["selection"]
    gates = {"none": pd.Series(1.0, index=idx)}
    for name in sig.columns:
        for q in (0.6, 0.8):
            gates[f"{name}|hard|{q}"] = make_gate(sig[name], sel, "hard", q)
            gates[f"{name}|soft|{q}"] = make_gate(sig[name], sel, "soft", q)

    combos = [(w, r) for w in evaluation.WEIGHTINGS for r in evaluation.REBALANCE_EVERY]
    targets = {c: target_path(ranked, evaluation.WEIGHTINGS[c[0]], c[1]) for c in combos}
    jobs = [(c, g) for c in combos for g in gates]
    with ProcessPoolExecutor(max_workers=8, initializer=_init, initargs=(panel.close, targets, gates, segments)) as pool:
        rows = [row for rs in pool.map(_run, jobs, chunksize=8) for row in rs]
    df = pd.DataFrame(rows)
    df.to_csv(out / "gate_grid.csv", index=False)

    med = df.groupby(["gate", "segment"])[["sharpe", "mdd", "calmar", "ann_ret", "in_market", "turnover"]].median().unstack("segment")
    both = df.pivot_table(index=["gate", "weighting", "rebalance_every"], columns="segment", values="sharpe")
    med[("both_pos", "")] = ((both["selection"] > 0) & (both["validation"] > 0)).groupby("gate").mean()
    base = df[df.gate == "none"].set_index(["weighting", "rebalance_every", "segment"])
    gd = df.set_index(["weighting", "rebalance_every", "segment"])
    win = []
    for gate, g in gd.groupby("gate"):
        d = g.join(base, rsuffix="_base")
        win.append({"gate": gate,
                    "mdd_better_val": float((d.xs("validation", level="segment").eval("mdd > mdd_base")).mean()),
                    "sharpe_better_val": float((d.xs("validation", level="segment").eval("sharpe > sharpe_base")).mean())})
    med = med.join(pd.DataFrame(win).set_index("gate"))
    med.columns = ["|".join(c).strip("|") if isinstance(c, tuple) else c for c in med.columns]
    med = med.sort_values("calmar|selection", ascending=False)
    med.to_csv(out / "gate_summary.csv")
    pd.set_option("display.width", 260)
    print(med.round(3).to_string())


if __name__ == "__main__":
    main()
