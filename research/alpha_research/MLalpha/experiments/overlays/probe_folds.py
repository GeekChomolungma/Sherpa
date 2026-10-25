"""快速探测：只用选择段的重训时点（服务期在 validation_start 之前），比较不同后端 / 超参数的样本外截面能力。

每个配置在选定的若干个重训时点上训练 n 个种子，对它服务的 20 天打分（种子平均），算：
- rank_ic：逐期 Spearman(打分, 6 根未来收益) 的均值（标签持有期 = V4 的 6 根）；
- ic_ir：同上的均值 / 标准差；
- spread_bps：每期打分前 10% 与后 10% 的平均 6 根收益之差（bps），Top-K 等权赚的就是这个；
- best：早停轮数（树的棵数 / epoch 数）。
用法：python probe_folds.py <out_dir> <folds 如 4,8,12,16> <seeds> <name=json配置> ...
  json 配置 = training_overrides 的一部分，比如 {"backend":"lstm","backend_params":{"seq_len":6}}
"""
import json
import pickle
import sys
import time
from pathlib import Path

ROOT = Path(r"D:/code-repo/Chomo/Sherpa")
sys.path.insert(0, str(ROOT / "research" / "ml_training"))

import numpy as np
import pandas as pd

import config
from data import EXECUTION_DELAY_BARS, INTERVAL, START_TIME, VALIDATION_START
from dataset import build_training_frame, plan_folds, split_inner_validation
from trainer import train_fold
from sherpa.alpha.custom.ml.backends import get_backend, predict_ensemble
from sherpa.alpha.custom.ml.models import LgbmV4

out = Path(sys.argv[1])
fold_ids = [int(x) for x in sys.argv[2].split(",")]
n_seeds = int(sys.argv[3])
configs = dict(a.split("=", 1) for a in sys.argv[4:])

panel = pickle.loads((ROOT / "research/alpha_research/MLalpha/experiments/_cache/panel_2023-01-01_2026-03-15.pkl").read_bytes())
base = dict(LgbmV4.training_overrides)
cfg0 = config.for_model(base)
frame = build_training_frame(panel, LgbmV4.spec, horizon=6, delay=EXECUTION_DELAY_BARS, neutralize_label=False,
                             tail_quantile=cfg0.tail_quantile, tail_weight=cfg0.tail_weight, label_transform="raw_clip")
folds = plan_folds(research_start=pd.Timestamp(START_TIME, tz="UTC"), last_bar=panel.index[-1], interval=INTERVAL,
                   retrain_every_bars=cfg0.retrain_every_bars, min_train_bars=cfg0.min_train_bars, purge_bars=7,
                   train_window_bars=None)
vstart = pd.Timestamp(VALIDATION_START, tz="UTC")
for i in fold_ids:
    assert folds[i].valid_until <= vstart, f"fold {i} 服务期伸进了验证段"


def stats(pred, label, times):
    df = pd.DataFrame({"p": pred, "y": label, "t": times})
    ics, spreads = [], []
    for _, g in df.groupby("t"):
        if len(g) < 20:
            continue
        ics.append(g["p"].rank().corr(g["y"].rank()))
        q = g["p"].rank(pct=True)
        spreads.append(g.loc[q >= 0.9, "y"].mean() - g.loc[q <= 0.1, "y"].mean())
    ics = np.array(ics)
    return ics, np.array(spreads)


rows = []
for name, raw in configs.items():
    overrides = {**base, **json.loads(raw), "seeds": list(range(n_seeds))}
    cfg = config.for_model(overrides)
    backend = get_backend(cfg.backend)
    all_ic, all_sp, best_all = [], [], []
    started = time.monotonic()
    for i in fold_ids:
        fold = folds[i]
        rows_ = frame.rows_between(fold.train_from, fold.train_until)
        fit, valid = split_inner_validation(frame, rows_, train_until=fold.train_until, valid_bars=cfg.inner_valid_bars,
                                            purge_bars=7, interval=INTERVAL)
        rel = f"f{i}"
        res = train_fold(frame, fit, valid, out / name / rel, full=rows_, objective=cfg.objective, seeds=cfg.seeds,
                         lgb_params=cfg.lgb_params, num_boost_round=cfg.num_boost_round,
                         early_stopping_rounds=cfg.early_stopping_rounds, min_period_rows=cfg.min_period_rows,
                         rel_prefix=rel, backend=cfg.backend, backend_params=cfg.backend_params)
        serve = frame.rows_between(fold.valid_from, fold.valid_until, end_inclusive=False)
        idx = np.arange(serve.start, serve.stop)
        pred = predict_ensemble(backend, out / name, res.files, frame.inputs, frame.source_rows[idx])
        ic, sp = stats(pred, frame.label[idx], frame.times[idx].asi8)
        all_ic.append(ic); all_sp.append(sp); best_all += res.best_iterations
    ic = np.concatenate(all_ic); sp = np.concatenate(all_sp)
    rows.append({"config": name, "rank_ic": ic.mean(), "ic_ir": ic.mean() / ic.std(), "spread_bps": sp.mean() * 1e4,
                 "spread_t": sp.mean() / sp.std() * np.sqrt(len(sp) / 6), "best_med": float(np.median(best_all)),
                 "minutes": (time.monotonic() - started) / 60})
    print(pd.DataFrame(rows[-1:]).round(4).to_string(index=False), flush=True)
print("\n" + pd.DataFrame(rows).round(4).to_string(index=False))
