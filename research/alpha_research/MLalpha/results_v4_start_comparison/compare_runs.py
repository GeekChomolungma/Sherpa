"""两次正式运行（不同研究起点）的 V4 模型，在相同时段上按关卡3 口径（同一套 39 个组合、同样的打分预处理）比较。

用法：python compare_runs.py <面板缓存 .pkl> <out_dir> <label=模型类名:模型目录名> ...
  面板缓存用探索的 experiments/_cache/panel_2023-01-01_2026-03-15.pkl（研究段全市场 4h，含 OI / 多空比）
产出：<out_dir>/common_04_robustness.csv、common_05_style_attribution.csv、common_06_quarterly.csv、common_periods.json
"""
import json, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(r"D:/code-repo/Chomo/Sherpa")
sys.path.insert(0, str(ROOT / "research" / "friction_test"))
import config  # friction_test/config.py：39 个组合 + 成本
from sherpa.alpha.custom.ml import models as ml_models
from sherpa.backtest.attribution import attribute, period_stats, style_factor_returns
from sherpa.backtest.residual import ScorePreprocessor, residual_score
from sherpa.backtest.score_backtest import cost_segment_rows, cross_sectional_rank, run_score_backtest, target_path

PANEL, OUT = sys.argv[1], Path(sys.argv[2])
runs = dict(a.split("=", 1) for a in sys.argv[3:])
OUT.mkdir(parents=True, exist_ok=True)
panel = pickle.load(open(PANEL, "rb"))
ppy = 6 * 365; shift = 2
import os
PERIODS = json.loads(os.environ["PERIODS"]) if os.environ.get("PERIODS") else {
    "A_2024-06-29~2025-03-01": ("2024-06-29", "2025-03-01"), "B_2025-03-01~2026-03-15": ("2025-03-01", "2026-03-16")}
json.dump(PERIODS, open(OUT / "common_periods.json", "w"), indent=2)
pre = ScorePreprocessor.from_panel(panel, benchmark_symbol="BTCUSDT",
                                   tradable={"min_percentile": 0.5, "min_quote_volume": 0, "min_trades_count": 0}, neutralize=False)
style = style_factor_returns(panel.close, panel.quote_volume, pre.mask, interval="4h", shift=shift, benchmark_symbol="BTCUSDT")
segments = {name: pd.Series((panel.index >= pd.Timestamp(a, tz="UTC")) & (panel.index < pd.Timestamp(b, tz="UTC")), index=panel.index)
            for name, (a, b) in PERIODS.items()}
rob, att, qtr = [], [], []
for label, model_dir in runs.items():
    cls_name, model_dir = model_dir.split(":")  # 参数格式 label=类名:模型目录名
    alpha = type("Run", (getattr(ml_models, cls_name),), {"model_name": model_dir})()
    score = cross_sectional_rank(residual_score(alpha, panel, pre))
    for w in config.WEIGHTINGS:
        for reb in config.REBALANCE_EVERY:
            gross, turnover = run_score_backtest(target_path(score, config.WEIGHTINGS[w], reb), panel.close, "4h", shift=shift, rebalance_every=reb)
            key = {"run": label, "weighting": w, "rebalance_every": reb}
            rob += [{**key, **r} for r in cost_segment_rows(gross, turnover, config.COST_MODELS, segments, periods_per_year=ppy)]
            net = gross - turnover.map(config.COST_MODELS[config.BASE_COST].cost)
            for name, m in segments.items():
                att.append({**key, "segment": name, **attribute(net[m.reindex(net.index, fill_value=False)], style, periods_per_year=ppy)})
            first = pd.Timestamp(list(PERIODS.values())[0][0], tz="UTC")
            q = period_stats(net[net.index >= first], periods_per_year=ppy)
            full = q["return"].dropna()
            qtr.append({**key, "quarters": len(full), "positive_quarter_frac": float((full > 0).mean()),
                        **{f"return[{p}]": v for p, v in q["return"].items()}})
    print(label, "done", flush=True)
rob = pd.DataFrame(rob); att = pd.DataFrame(att); qtr = pd.DataFrame(qtr)
rob.to_csv(OUT / "common_01_summary.csv", index=False); att.to_csv(OUT / "common_05_style_attribution.csv", index=False)
qtr.to_csv(OUT / "common_06_quarterly.csv", index=False)
# 04 口径：每个 run × 成本，两段中位数 / 为正占比 / 两段都为正
wide = rob.pivot_table(index=["run", "cost_model", "weighting", "rebalance_every"], columns="segment", values="net_sharpe")
a, b = list(PERIODS)
r04 = wide.groupby(level=["run", "cost_model"]).apply(lambda g: pd.Series({
    "n_combos": len(g), f"{a}_median": g[a].median(), f"{b}_median": g[b].median(),
    f"{a}_pos": (g[a] > 0).mean(), f"{b}_pos": (g[b] > 0).mean(), "both_positive_frac": ((g[a] > 0) & (g[b] > 0)).mean()}))
r04.to_csv(OUT / "common_04_robustness.csv")
pd.set_option("display.width", 250)
print(r04.round(3).to_string())
print(att.groupby(["run", "segment"])[["raw_sharpe", "alpha_sharpe", "beta[low_vol]", "beta[reversal]", "r2"]].median().round(3).to_string())
print(qtr.groupby("run")["positive_quarter_frac"].median().round(3).to_string())
