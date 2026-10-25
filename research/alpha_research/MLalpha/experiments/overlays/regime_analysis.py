"""一个 case 的打分：吃单净值曲线的回撤在哪、跟什么行情有关、有没有决策时点就能拿到的信号能提前识别"不该参与"的时段。

用法：python regime_analysis.py <scores.pkl> <out_dir> [weighting] [rebalance]

时间口径跟关卡3 一样：第 t 行 = t 收盘决策的持仓，赚 close[t+1] -> close[t+2]（shift = 1 + delay = 2）。所以 t 时刻已知的
策略收益 / 已实现 IC 只到 t-2 行（`known = x.shift(2)`）。所有信号都只用 <= t 的数据。
"""
import pickle
import sys
from pathlib import Path

ROOT = Path(r"D:/code-repo/Chomo/Sherpa")
sys.path.insert(0, str(ROOT / "research" / "ml_training"))

import numpy as np
import pandas as pd

import evaluation
from data import VALIDATION_START
from sherpa.alpha.custom.ml.features import market_features
from sherpa.alpha.custom.ml.models import LgbmV4
from sherpa.backtest.score_backtest import cross_sectional_rank, run_score_backtest, target_path
from sherpa.metrics.factor import forward_returns

scores_path, out = Path(sys.argv[1]), Path(sys.argv[2])
weighting = sys.argv[3] if len(sys.argv) > 3 else "top10_exit50"
rebalance = int(sys.argv[4]) if len(sys.argv) > 4 else 3
out.mkdir(parents=True, exist_ok=True)
COST = 8e-4  # all_taker：5 bps 手续费 + 3 bps 滑点
PPY = 6 * 365

panel = pickle.loads((ROOT / "research/alpha_research/MLalpha/experiments/_cache/panel_2023-01-01_2026-03-15.pkl").read_bytes())
scope = LgbmV4.spec.liquidity.mask(panel)
raw = pd.read_pickle(scores_path).reindex(index=panel.close.index, columns=panel.close.columns).where(scope)
ranked = cross_sectional_rank(raw)
active = ranked.notna().any(axis=1)
start = active.idxmax()
vstart = pd.Timestamp(VALIDATION_START, tz="UTC")

targets = target_path(ranked, evaluation.WEIGHTINGS[weighting], rebalance)
gross, turnover = run_score_backtest(targets, panel.close, "4h", shift=2, rebalance_every=rebalance)
net = (gross - turnover * COST)[lambda s: s.index >= start]
seg = pd.Series(np.where(net.index < vstart, "selection", "validation"), index=net.index)


def sharpe(r):
    return r.mean() / r.std() * np.sqrt(PPY) if r.std() > 0 else np.nan


def mdd(r):
    eq = (1 + r).cumprod()
    return (eq / eq.cummax() - 1).min()


print(f"{weighting} every{rebalance}: sel Sharpe {sharpe(net[seg == 'selection']):.2f} MDD {mdd(net[seg == 'selection']):.1%} | "
      f"val Sharpe {sharpe(net[seg == 'validation']):.2f} MDD {mdd(net[seg == 'validation']):.1%}")

# ---- 1. 最大的几次回撤 ----
eq = (1 + net).cumprod()
dd = eq / eq.cummax() - 1
episodes = []
in_dd, peak_t = False, net.index[0]
for t, v in dd.items():
    if v == 0:
        if in_dd:
            episodes.append((peak_t, trough_t, t, trough_v))
            in_dd = False
        peak_t = t
    else:
        if not in_dd or v < trough_v:
            trough_t, trough_v = t, v
        in_dd = True
if in_dd:
    episodes.append((peak_t, trough_t, None, trough_v))
episodes = sorted(episodes, key=lambda e: e[3])[:8]

mf = market_features(panel, LgbmV4.spec).reindex(net.index)
btc_ret = panel.close["BTCUSDT"].pct_change(fill_method=None).reindex(net.index)
print("\n== 最大回撤 ==")
ep_rows = []
for peak, trough, end, depth in episodes:
    span = (net.index > peak) & (net.index <= trough)
    ep_rows.append({
        "peak": peak, "trough": trough, "recovered": end, "depth": depth,
        "days_down": (trough - peak).days,
        "btc_ret_in_dd": float((1 + btc_ret[span]).prod() - 1),
        "rv_q": float(mf.loc[span, "rv_quantile"].mean()), "disp_q": float(mf.loc[span, "dispersion_quantile"].mean()),
        "breadth": float(mf.loc[span, "market_breadth"].mean()),
    })
ep = pd.DataFrame(ep_rows)
print(ep.round(3).to_string(index=False))
ep.to_csv(out / "drawdowns.csv", index=False)

# ---- 2. 候选信号（t 时刻已知） ----
label1 = forward_returns(panel.close, horizon=1, delay=1).where(scope)
both = ranked.notna() & label1.notna()
ic = ranked.where(both).rank(axis=1).corrwith(label1.where(both).rank(axis=1), axis=1)  # 第 t 行的 IC，t+2 才知道
known_net = net.reindex(panel.close.index).shift(2)
known_ic = ic.shift(2)
spread_raw = raw.quantile(0.9, axis=1) - raw.quantile(0.1, axis=1)  # 模型原始打分的首尾差：信心强弱
signals = {
    "pnl_42": known_net.rolling(42, min_periods=30).sum(),        # 策略近 7 天已实现收益
    "pnl_120": known_net.rolling(120, min_periods=90).sum(),      # 近 20 天
    "ic_42": known_ic.rolling(42, min_periods=30).mean(),        # 模型近 7 天已实现 IC
    "ic_120": known_ic.rolling(120, min_periods=90).mean(),
    "score_spread_rel": spread_raw / spread_raw.rolling(120, min_periods=60).median(),
    "rv_quantile": mf["rv_quantile"],
    "dispersion_quantile": mf["dispersion_quantile"],
    "market_breadth": mf["market_breadth"],
    "benchmark_ret_42": mf["benchmark_ret_42"],
    "abs_benchmark_ret_42": mf["benchmark_ret_42"].abs(),
    "volume_quantile": mf["volume_quantile"],
}
sig = pd.DataFrame(signals).reindex(net.index)
sig.to_pickle(out / "signals.pkl")
net.to_pickle(out / "net.pkl")

print("\n== 按信号分桶：下一根的策略净收益（每根 bps 均值 / 年化 Sharpe），桶边界取选择段的五分位 ==")
rows = []
for name in sig.columns:
    x = sig[name]
    edges = x[seg == "selection"].quantile([0.2, 0.4, 0.6, 0.8]).to_numpy()
    if not np.isfinite(edges).all() or len(np.unique(edges)) < 4:
        continue
    bucket = pd.Series(np.searchsorted(edges, x.to_numpy(), side="right"), index=x.index).where(x.notna())
    for s in ("selection", "validation"):
        for b in range(5):
            r = net[(seg == s) & (bucket == b)]
            rows.append({"signal": name, "segment": s, "bucket": b + 1, "bars": len(r), "bps": r.mean() * 1e4, "sharpe": sharpe(r)})
tab = pd.DataFrame(rows)
tab.to_csv(out / "signal_buckets.csv", index=False)
wide = tab.pivot_table(index=["signal", "segment"], columns="bucket", values="sharpe")
print(wide.round(2).to_string())
