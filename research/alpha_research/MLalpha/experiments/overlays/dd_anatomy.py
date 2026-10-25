"""拆一个 case 的回撤：逐月的 IC（排序能力）、多头腿 / 空头腿各自的收益、同期风格收益。

用法：python dd_anatomy.py <scores.pkl> [weighting] [rebalance]
多 / 空腿：把目标权重拆成正 / 负两部分各自回测（零成本，按各自 0.5 敞口），收益口径同关卡3（shift = 2）。
"""
import pickle
import sys
from pathlib import Path

ROOT = Path(r"D:/code-repo/Chomo/Sherpa")
sys.path.insert(0, str(ROOT / "research" / "ml_training"))

import numpy as np
import pandas as pd

import evaluation
from sherpa.alpha.custom.ml.models import LgbmV4
from sherpa.backtest.attribution import style_factor_returns
from sherpa.backtest.score_backtest import cross_sectional_rank, run_score_backtest, target_path
from sherpa.metrics.factor import forward_returns

weighting = sys.argv[2] if len(sys.argv) > 2 else "top10_exit50"
rebalance = int(sys.argv[3]) if len(sys.argv) > 3 else 3
panel = pickle.loads((ROOT / "research/alpha_research/MLalpha/experiments/_cache/panel_2023-01-01_2026-03-15.pkl").read_bytes())
scope = LgbmV4.spec.liquidity.mask(panel)
raw = pd.read_pickle(sys.argv[1]).reindex(index=panel.close.index, columns=panel.close.columns).where(scope)
ranked = cross_sectional_rank(raw)
start = ranked.notna().any(axis=1).idxmax()

targets = target_path(ranked, evaluation.WEIGHTINGS[weighting], rebalance)
legs = {}
for name, part in (("long", targets.clip(lower=0)), ("short", targets.clip(upper=0))):
    gross, turnover = run_score_backtest(part, panel.close, "4h", shift=2, rebalance_every=rebalance)
    legs[name] = gross
gross, turnover = run_score_backtest(targets, panel.close, "4h", shift=2, rebalance_every=rebalance)
legs["net"] = gross - turnover * 8e-4

label6 = forward_returns(panel.close, horizon=6, delay=1).where(scope)
both = ranked.notna() & label6.notna()
ic = ranked.where(both).rank(axis=1).corrwith(label6.where(both).rank(axis=1), axis=1)
# 首尾 10% 的 6 根平均收益之差：Top-K 真正赚的东西
q = ranked.rank(axis=1, pct=True)
spread = label6.where(q >= 0.9).mean(axis=1) - label6.where(q <= 0.1).mean(axis=1)

style = style_factor_returns(panel.close, panel.quote_volume, scope, interval="4h", shift=2, benchmark_symbol="BTCUSDT")
df = pd.DataFrame({**legs, "ic6": ic, "spread6": spread / 6}).join(style)
df = df[df.index >= start]
df.index = df.index.tz_localize(None)
m = df.resample("ME").agg({**{c: "sum" for c in ["long", "short", "net", "spread6", *style.columns]}, "ic6": "mean"})
m["btc_month"] = (1 + df["btc"]).resample("ME").prod() - 1
pd.set_option("display.width", 250)
cols = ["net", "long", "short", "ic6", "spread6", "btc_month", "market", "low_vol", "small_size", "reversal", "momentum"]
print(f"{weighting} every{rebalance}：逐月（收益为月内逐 bar 简单加总；ic6 = 月内平均 6 根 RankIC；spread6 = 首尾 10% 每根价差加总）")
print((m[cols] * [100, 100, 100, 1, 100, 100, 100, 100, 100, 100, 100]).round(2).to_string())
