"""ML alpha 的探索实验：一批配置（case）各自滚动训练、样本外打分，用关卡3 同口径的扣费回测比较，找盈利点。

    CH_HOST=... CH_PASSWORD=... python research/ml_training/run_experiments.py                 # 跑全部 case
    python research/ml_training/run_experiments.py --cases h6,h6_raw                            # 只跑指定的
    python research/ml_training/run_experiments.py --summary-only                               # 只重新汇总

跟正式训练（`run_training.py`）的关系：训练用的是同一套函数（`dataset.build_training_frame` / `plan_folds` /
`split_inner_validation`、`trainer.train_fold` 两步训练），只是配置不从 `config.py` 读，而是每个 case 自己给；
评估用 `evaluation.py`（关卡3 同口径的拷贝）。所以这里挑出来的配置，搬进 `config.py` / `models.py` 后走正式流水线，
结果应该一致（`v2_official` vs `v2_retrain` 两个 case 就是用来核对这一点的）。

**怎么挑配置才不自欺**：每个模型都是滚动训练的，选择段和验证段的打分都是样本外的。汇总表按**选择段**的扣费净 Sharpe
挑每个 case 的最好组合（映射 × 调仓频率 × 平滑），再报告**同一组合**在验证段的表现——验证段只用来确认，不用来挑。
holdout 全程不碰。B 组特征名单是在选择段上选出来的，选择段数字仍偏乐观。

产出（`research/alpha_research/MLalpha/experiments/`，CSV / 模型 / 缓存都不进 git）：
- `<case>/folds.csv`：每个重训时点的早停轮数、内部验证 IC_IR；
- `<case>/diagnostics.csv`：选择段 / 验证段 × 平滑：RankIC、Pearson IC、首尾价差、vol 暴露；
- `<case>/friction_grid.csv`：平滑 × 映射 × 调仓频率 × 成本 × 段的完整绩效长表；
- `<case>/scores.pkl`：样本外打分 (T, N)；`<case>/models/`：模型文件；
- `summary.csv`：每个 case 一行（按选择段挑的最好组合 + 它在验证段的表现 + 诊断）。
"""

from __future__ import annotations

import argparse
import dataclasses
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

from sherpa.alpha.custom.ml import LgbmV1
from sherpa.alpha.custom.ml.features import FeatureSpec, build_features
from sherpa.alpha.liquidity import LiquidityFilter
from sherpa.data.schema import interval_to_timedelta
from sherpa.metrics.factor import forward_returns
from sherpa.metrics.tradability import DEFAULT_LOOKBACK, SEASONING_PERIOD

import config
import evaluation
from data import END_TIME, EXECUTION_DELAY_BARS, INTERVAL, START_TIME, VALIDATION_START, load_universe_panel
from dataset import TrainingFrame, build_training_frame, plan_folds, split_inner_validation
from trainer import train_fold

OUT_DIR = Path(__file__).resolve().parents[1] / "alpha_research" / "MLalpha" / "experiments"
CACHE_DIR = OUT_DIR / "_cache"
SMOOTH_HALFLIVES: tuple[float, ...] = (0, 3, 6)


@dataclass(frozen=True)
class Case:
    """一个实验配置。没写的项 = 正式训练当前的配置（config.py / LgbmV1.spec，2026-10-05）。"""

    name: str
    note: str
    source: str = "train"                       # "train"：本脚本滚动训练；"official"：直接用正式模型（MLAlpha.compute）；
                                                # "factor:<名字>"：不用 ML，直接拿单个原始特征打分（FACTORS），方向按选择段 IC 符号定；
                                                # "blend:<case1>+<case2>+..."：几个已跑完 case 的打分取截面排名的平均（更多种子的集成）
    neutralize_scores: tuple[str, ...] = ()     # 打分出来后，逐期截面回归剥离这些暴露再交易：可选 "vol42" / "beta" / "size"
    horizon: int = 1                            # 标签持有期（根 bar）；执行延迟固定用 research_config 的
    label_transform: str = "rank"               # "rank" / "raw_clip"
    objective: str = "ic_ir"                    # "ic_ir" / "l2_rank"
    tail_quantile: float = config.TAIL_QUANTILE
    tail_weight: float = config.TAIL_WEIGHT
    window_bars: Optional[int] = config.TRAIN_WINDOW_BARS
    valid_bars: int = config.INNER_VALID_BARS
    neutralize_label: bool = False
    drop_features: tuple[str, ...] = ()         # 按前缀去掉的特征，比如 ("alpha:",) = 不要 B 组
    min_percentile: float = 0.5                 # 流动性范围（特征排名 + 损失 + 评估）
    lgb_overrides: tuple[tuple[str, Any], ...] = ()
    seeds: tuple[int, ...] = config.SEEDS

    @property
    def spec(self) -> FeatureSpec:
        return FeatureSpec(
            name="lgbm_v1", version=1, alphas=LgbmV1.spec.alphas,
            liquidity=LiquidityFilter(min_percentile=self.min_percentile, seasoning_period=SEASONING_PERIOD, lookback=DEFAULT_LOOKBACK),
        )


# 单因子基线（source="factor:<名字>"）：原始值，panel -> (T, N)；方向在 evaluate 前按选择段 RankIC 的符号统一成"越大越好"
FACTORS = {
    "ret_1": lambda p: p.close.pct_change(1, fill_method=None),
    "ret_6": lambda p: p.close.pct_change(6, fill_method=None),
    "ret_42": lambda p: p.close.pct_change(42, fill_method=None),
    "ret_120": lambda p: p.close.pct_change(120, fill_method=None),
    "vol_42": lambda p: p.close.pct_change(fill_method=None).rolling(42).std(),
    "quote_volume_42": lambda p: p.quote_volume.rolling(42).mean(),
    "quote_volume_surge_6_42": lambda p: p.quote_volume.rolling(6).mean() / p.quote_volume.rolling(42).mean(),
    "taker_buy_ratio_6": lambda p: p.taker_buy_quote_volume.rolling(6).sum() / p.quote_volume.rolling(6).sum(),
    "oi_change_6": lambda p: p.open_interest.pct_change(6, fill_method=None),
    "oi_change_42": lambda p: p.open_interest.pct_change(42, fill_method=None),
    "dist_high_42": lambda p: p.close / p.high.rolling(42).max() - 1,
}

H6 = dict(horizon=6)
CASES: list[Case] = [
    # ---- 基线：核对本脚本跟正式流水线一致 ----
    Case("v2_official", "正式流水线当前的模型（第二版），用来核对评估口径跟关卡3 一致", source="official"),
    Case("v2_retrain", "本脚本按第二版配置重训，用来核对训练路径跟正式训练一致"),
    # ---- 标签持有期：信号越慢、换手越低 ----
    Case("h3", "标签持有 3 根（12 小时）", horizon=3),
    Case("h6", "标签持有 6 根（1 天）", **H6),
    Case("h12", "标签持有 12 根（2 天）", horizon=12),
    # ---- 标签形态：排名 vs 原始收益 ----
    Case("h1_raw", "持有 1 根，原始收益标签（1% 截尾）", label_transform="raw_clip"),
    Case("h6_raw", "持有 1 天，原始收益标签", label_transform="raw_clip", **H6),
    # ---- 训练窗口 ----
    Case("h6_win180", "持有 1 天，滑动 180 天窗口", window_bars=6 * 180, **H6),
    Case("h6_win365", "持有 1 天，滑动 365 天窗口", window_bars=6 * 365, **H6),
    Case("h6_expanding", "持有 1 天，扩展窗口", window_bars=None, **H6),
    # ---- 损失 ----
    Case("h6_l2rank", "持有 1 天，排名标签上的 MSE 回归", objective="l2_rank", **H6),
    Case("h6_notail", "持有 1 天，不做首尾加权", tail_weight=1.0, **H6),
    Case("h6_neutral", "持有 1 天，标签剥离 Beta / Size", neutralize_label=True, **H6),
    # ---- 特征消融 ----
    Case("h6_noB", "持有 1 天，去掉 B 组（世坤因子）", drop_features=("alpha:",), **H6),
    Case("h6_noC", "持有 1 天，去掉 C 组（市场状态）", drop_features=("market:",), **H6),
    # ---- 流动性范围 ----
    Case("h6_p70", "持有 1 天，只用成交额截面前 30% 的币", min_percentile=0.7, **H6),
    # ---- 剥离暴露：去掉低波动 / Beta 倾向之后还剩多少 ----
    Case("v2_resid_vol", "正式模型打分，剥离 vol_42 暴露", source="official", neutralize_scores=("vol42",)),
    Case("v2_resid_vol_beta", "正式模型打分，剥离 vol_42 + Beta 暴露", source="official", neutralize_scores=("vol42", "beta")),
    # ---- 单因子基线：不用 ML，这个币池里单个原始特征能不能赚钱 ----
    *[Case(f"f_{name}", f"单因子 {name}（方向按选择段 IC 定）", source=f"factor:{name}") for name in FACTORS],
    # ---- 第三批：围绕 h6_raw（持有 1 天 + 原始收益标签）----
    Case("h6_raw_seed345", "h6_raw 换一组随机种子（3,4,5），看是不是运气", label_transform="raw_clip", seeds=(3, 4, 5), **H6),
    Case("h6_raw_p70", "h6_raw + 只用成交额前 30% 的币", label_transform="raw_clip", min_percentile=0.7, **H6),
    Case("h6_raw_p60", "h6_raw + 只用成交额前 40% 的币", label_transform="raw_clip", min_percentile=0.6, **H6),
    Case("h3_raw", "持有 12 小时 + 原始收益标签", label_transform="raw_clip", horizon=3),
    Case("h12_raw", "持有 2 天 + 原始收益标签", label_transform="raw_clip", horizon=12),
    Case("h6_raw_win180", "h6_raw + 滑动 180 天窗口", label_transform="raw_clip", window_bars=6 * 180, **H6),
    Case("h6_raw_expanding", "h6_raw + 扩展窗口", label_transform="raw_clip", window_bars=None, **H6),
    Case("h6_raw_l2", "h6_raw + MSE 回归（对截尾后的原始收益）", label_transform="raw_clip", objective="l2_rank", **H6),
    Case("h6_raw_notail", "h6_raw + 不做首尾加权", label_transform="raw_clip", tail_weight=1.0, **H6),
    Case("h6_raw_neutral", "h6_raw + 标签剥离 Beta / Size", label_transform="raw_clip", neutralize_label=True, **H6),
    Case("h6_raw_noB", "h6_raw + 去掉 B 组（世坤因子）", label_transform="raw_clip", drop_features=("alpha:",), **H6),
    Case("h6_raw_noC", "h6_raw + 去掉 C 组（市场状态）", label_transform="raw_clip", drop_features=("market:",), **H6),
    # ---- 第四批：多种子集成（单个模型树少、随机性大，两组种子的打分截面相关只有 0.43）----
    Case("h6_raw_ens6", "h6_raw 两组种子（0-2、3-5）共 6 个模型的打分平均", source="blend:h6_raw+h6_raw_seed345", **H6),
    Case("h6_raw_seed6789", "h6_raw 第三组种子（6,7,8,9）", label_transform="raw_clip", seeds=(6, 7, 8, 9), **H6),
    Case("h6_raw_seed1013", "h6_raw 第四组种子（10,11,12,13）", label_transform="raw_clip", seeds=(10, 11, 12, 13), **H6),
    Case("h6_raw_ens14", "h6_raw 四组种子共 14 个模型的打分平均",
         source="blend:h6_raw+h6_raw_seed345+h6_raw_seed6789+h6_raw_seed1013", **H6),
    # ---- 第五批：扩展窗口 + 原始收益标签（两段整体最均衡）的多种子集成 ----
    Case("h6_raw_exp_seed345", "h6_raw_expanding 换种子（3,4,5）", label_transform="raw_clip", window_bars=None, seeds=(3, 4, 5), **H6),
    Case("h6_raw_exp_seed678", "h6_raw_expanding 换种子（6,7,8）", label_transform="raw_clip", window_bars=None, seeds=(6, 7, 8), **H6),
    Case("h6_raw_exp_ens9", "h6_raw_expanding 三组种子共 9 个模型的打分平均",
         source="blend:h6_raw_expanding+h6_raw_exp_seed345+h6_raw_exp_seed678", **H6),
]


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------

def load_panel(refresh: bool):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"panel_{START_TIME}_{END_TIME}.pkl"
    if path.exists() and not refresh:
        return pickle.loads(path.read_bytes())
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线……", flush=True)
    panel = load_universe_panel()
    path.write_bytes(pickle.dumps(panel, protocol=pickle.HIGHEST_PROTOCOL))
    return panel


_FEATURE_CACHE: dict[float, tuple[pd.DataFrame, pd.DataFrame]] = {}


def scope_and_features(panel, case: Case) -> tuple[pd.DataFrame, pd.DataFrame]:
    if case.min_percentile not in _FEATURE_CACHE:
        spec = case.spec
        scope = spec.liquidity.mask(panel)
        _FEATURE_CACHE[case.min_percentile] = (scope, build_features(panel, spec, scope))
    return _FEATURE_CACHE[case.min_percentile]


def _keep_columns(names: list[str], drop: tuple[str, ...]) -> list[int]:
    return [i for i, n in enumerate(names) if not any(n.startswith(p) for p in drop)]


# ---------------------------------------------------------------------------
# 训练 + 样本外打分
# ---------------------------------------------------------------------------

def train_case(panel, case: Case, case_dir: Path) -> pd.DataFrame:
    scope, features = scope_and_features(panel, case)
    frame = build_training_frame(
        panel, case.spec, horizon=case.horizon, delay=EXECUTION_DELAY_BARS, neutralize_label=case.neutralize_label,
        tail_quantile=case.tail_quantile, tail_weight=case.tail_weight, label_transform=case.label_transform,
        scope=scope, features=features,
    )
    cols = _keep_columns(frame.feature_names, case.drop_features)
    frame = dataclasses.replace(frame, features=frame.features[:, cols], feature_names=[frame.feature_names[i] for i in cols])

    # 打分用全部范围内的行（不只是标签已知的行：标签未知的行，比如快下架的币，实盘时照样要打分）
    times = pd.DatetimeIndex(features.index.get_level_values("start_time"))
    symbols = features.index.get_level_values("symbol")
    in_scope = scope.to_numpy()[panel.close.index.get_indexer(times), panel.close.columns.get_indexer(symbols)]
    matrix = features.to_numpy(dtype="float32")[:, cols]
    preds = np.full(len(features), np.nan)

    purge = case.horizon + EXECUTION_DELAY_BARS
    folds = plan_folds(
        research_start=pd.Timestamp(START_TIME, tz="UTC"), last_bar=panel.index[-1], interval=INTERVAL,
        retrain_every_bars=config.RETRAIN_EVERY_BARS, min_train_bars=config.MIN_TRAIN_BARS, purge_bars=purge,
        train_window_bars=case.window_bars,
    )
    params = {**config.LGB_PARAMS, **dict(case.lgb_overrides)}
    fold_rows = []
    import lightgbm as lgb

    for fold in folds:
        rows = frame.rows_between(fold.train_from, fold.train_until)
        fit, valid = split_inner_validation(
            frame, rows, train_until=fold.train_until, valid_bars=case.valid_bars, purge_bars=purge, interval=INTERVAL
        )
        rel = fold.valid_from.strftime("%Y%m%dT%H%M")
        result = train_fold(
            frame, fit, valid, case_dir / "models" / rel, full=rows, objective=case.objective, seeds=case.seeds,
            lgb_params=params, num_boost_round=config.NUM_BOOST_ROUND, early_stopping_rounds=config.EARLY_STOPPING_ROUNDS,
            min_period_rows=config.MIN_PERIOD_ROWS, rel_prefix=rel,
        )
        lo, hi = times.searchsorted(fold.valid_from, "left"), times.searchsorted(fold.valid_until, "left")
        serve = np.zeros(len(features), dtype=bool)
        serve[lo:hi] = True
        serve &= in_scope
        if serve.any():
            boosters = [lgb.Booster(model_file=str(case_dir / "models" / f)) for f in result.files]
            preds[serve] = np.mean([b.predict(matrix[serve]) for b in boosters], axis=0)
        fold_rows.append({"valid_from": fold.valid_from, "n_window_rows": rows.stop - rows.start,
                          "best_iterations": "|".join(map(str, result.best_iterations)),
                          "inner_valid_ic_ir": float(np.mean(result.metrics["inner_valid_ic_ir_by_seed"]))})
    pd.DataFrame(fold_rows).to_csv(case_dir / "folds.csv", index=False)
    scores = pd.Series(preds, index=features.index).unstack("symbol")
    return scores.reindex(index=panel.close.index, columns=panel.close.columns)


def official_scores(panel) -> pd.DataFrame:
    return LgbmV1().compute(panel)


def factor_scores(panel, case: Case) -> pd.DataFrame:
    """单因子：原始值套流动性范围，方向按**选择段**（研究起点 ~ validation_start）RankIC 的符号统一成"越大越好"。"""
    scope, _ = scope_and_features(panel, case)
    raw = FACTORS[case.source.split(":", 1)[1]](panel)
    raw = raw.where(np.isfinite(raw)).where(scope)
    label = forward_returns(panel.close, horizon=case.horizon, delay=EXECUTION_DELAY_BARS).where(scope)
    sel = panel.close.index < pd.Timestamp(VALIDATION_START, tz="UTC")
    a, b = raw[sel], label[sel]
    both = a.notna() & b.notna()
    ic = a.where(both).rank(axis=1).corrwith(b.where(both).rank(axis=1), axis=1).mean()
    print(f"  {case.name}：选择段 RankIC {ic:+.4f} → {'原方向' if ic >= 0 else '反向'}", flush=True)
    return raw if ic >= 0 else -raw


def blend_scores(case: Case) -> pd.DataFrame:
    """几个已跑完 case 的样本外打分：各自逐期截面排名后取平均（任一缺失就是缺失）。"""
    names = case.source.split(":", 1)[1].split("+")
    ranked = [pd.read_pickle(OUT_DIR / n / "scores.pkl").rank(axis=1, pct=True) for n in names]
    total = ranked[0]
    for r in ranked[1:]:
        total = total + r
    return total / len(ranked)


def neutralize_scores(panel, scores: pd.DataFrame, names: tuple[str, ...]) -> pd.DataFrame:
    """逐期截面回归：打分 ~ 截距 + 所选暴露，取残差（sherpa.risk.neutralize）。"""
    from sherpa.backtest.style_exposure import default_style_exposures
    from sherpa.risk.neutralize import neutralize

    style = default_style_exposures(panel, benchmark_symbol=LgbmV1.spec.benchmark_symbol)
    available = {
        "vol42": panel.close.pct_change(fill_method=None).rolling(42).std(),
        "beta": style["beta"],
        "size": style["size"],
    }
    return neutralize(scores, {n: available[n] for n in names})


# ---------------------------------------------------------------------------
# 评估（多进程跑回测网格）
# ---------------------------------------------------------------------------

_W: dict[str, Any] = {}


def _init_worker(close, interval, smoothed, segments, shift, ppy):
    _W.update(close=close, interval=interval, smoothed=smoothed, segments=segments, shift=shift, ppy=ppy)


def _run_combo(args: tuple[float, str, int]) -> list[dict]:
    halflife, weighting, rebalance = args
    spec = evaluation.WEIGHTINGS[weighting]
    rows = evaluation.backtest(
        _W["smoothed"][halflife], _W["close"], _W["interval"], spec=spec,
        rebalance_every=rebalance, shift=_W["shift"], segments=_W["segments"], periods_per_year=_W["ppy"],
    )
    return [{"smooth": halflife, "weighting": weighting, "rebalance_every": rebalance, **r} for r in rows]


def evaluate_case(panel, case: Case, scores: pd.DataFrame, case_dir: Path, workers: int) -> None:
    scope, features = scope_and_features(panel, case)
    close = panel.close
    first = scores.dropna(how="all").index[0]
    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    segments = {
        "selection_oos": pd.Series((close.index >= first) & (close.index < validation_start), index=close.index),
        "validation": pd.Series(close.index >= validation_start, index=close.index),
    }
    ranked = evaluation.cross_sectional_rank(scores)
    smoothed = {h: evaluation.smooth(ranked, h) for h in SMOOTH_HALFLIVES}

    label_1 = forward_returns(close, horizon=1, delay=EXECUTION_DELAY_BARS).where(scope)
    label_h = forward_returns(close, horizon=case.horizon, delay=EXECUTION_DELAY_BARS).where(scope)
    vol = close.pct_change(fill_method=None).rolling(42).std()
    diag = []
    for h, sm in smoothed.items():
        diag += [{"smooth": h, **row} for row in evaluation.diagnostics(sm, label_1, label_h, vol, segments)]
    pd.DataFrame(diag).to_csv(case_dir / "diagnostics.csv", index=False)

    shift = 1 + EXECUTION_DELAY_BARS
    ppy = pd.Timedelta(days=365) / interval_to_timedelta(INTERVAL)
    combos = [(h, w, r) for h in SMOOTH_HALFLIVES for w in evaluation.WEIGHTINGS for r in evaluation.REBALANCE_EVERY]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(close, INTERVAL, smoothed, segments, shift, ppy)) as pool:
        grid = [row for rows in pool.map(_run_combo, combos) for row in rows]
    pd.DataFrame(grid).to_csv(case_dir / "friction_grid.csv", index=False)


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

KEY = ["smooth", "weighting", "rebalance_every"]
MAX_FLAT_FRACTION = 0.2


def summarize(cases: list[Case]) -> pd.DataFrame:
    rows = []
    for case in cases:
        d = OUT_DIR / case.name
        if not (d / "friction_grid.csv").exists():
            continue
        g = pd.read_csv(d / "friction_grid.csv")
        diag = pd.read_csv(d / "diagnostics.csv")
        sel = g[(g.segment == "selection_oos") & (g.cost_model == "all_taker")]
        if "flat_bar_fraction" in sel:  # 选择段空仓超过 20% 的组合不参与挑选：Sharpe 是在很少的交易 bar 上算的
            sel = sel[sel.flat_bar_fraction <= MAX_FLAT_FRACTION]
        if sel.empty:
            continue
        sel = sel.sort_values("net_sharpe", ascending=False)
        best = sel.iloc[0]
        pick = (g[KEY] == best[KEY]).all(axis=1)

        def at(segment, cost, col):
            return g.loc[pick & (g.segment == segment) & (g.cost_model == cost), col].iloc[0]

        val_taker = g[(g.segment == "validation") & (g.cost_model == "all_taker")]
        dv = diag[(diag.segment == "validation") & (diag.smooth == 0)].iloc[0]
        ds = diag[(diag.segment == "selection_oos") & (diag.smooth == 0)].iloc[0]
        # 稳健性：不平滑的 24 个组合（映射 × 调仓频率）在两段的扣费净 Sharpe 中位数、两段都为正的组合占比，
        # 以及零成本毛 Sharpe 的中位数——看的是"一片参数区域都成立"，不是网格里最高的那一格
        g0 = g[g.smooth == 0]
        if "flat_bar_fraction" in g0:
            usable = g0[(g0.segment == "selection_oos") & (g0.cost_model == "zero") & (g0.flat_bar_fraction <= MAX_FLAT_FRACTION)]
            g0 = g0.merge(usable[["weighting", "rebalance_every"]], on=["weighting", "rebalance_every"])
        wide = g0[g0.cost_model.isin(["all_taker", "zero"])].pivot_table(
            index=["weighting", "rebalance_every"], columns=["segment", "cost_model"], values="net_sharpe")
        both_pos = ((wide[("selection_oos", "all_taker")] > 0) & (wide[("validation", "all_taker")] > 0)).mean()
        rows.append({
            "case": case.name, "note": case.note,
            "sel_flat_frac": best.get("flat_bar_fraction", float("nan")),
            "sel_med_net_taker": wide[("selection_oos", "all_taker")].median(),
            "val_med_net_taker": wide[("validation", "all_taker")].median(),
            "sel_med_gross": wide[("selection_oos", "zero")].median(),
            "val_med_gross": wide[("validation", "zero")].median(),
            "both_pos_frac": both_pos,
            "sel_spread_top10_bps": ds["spread_top10_bps"],
            "pick": f"{best['weighting']}|every{int(best['rebalance_every'])}|hl{best['smooth']:g}",
            "sel_net_taker": best["net_sharpe"],
            "val_net_taker": at("validation", "all_taker", "net_sharpe"),
            "val_net_maker": at("validation", "all_maker", "net_sharpe"),
            "val_gross": at("validation", "zero", "gross_sharpe"),
            "val_ann_ret_taker": at("validation", "all_taker", "net_ann_return"),
            "val_maxdd_taker": at("validation", "all_taker", "net_max_drawdown"),
            "val_turnover": at("validation", "zero", "turnover_per_bar"),
            "val_breakeven_bps": at("validation", "zero", "breakeven_cost_bps"),
            "val_best_net_taker(偷看)": val_taker["net_sharpe"].max(),
            "val_rank_ic_1": dv["rank_ic_1"], "val_rank_ic_h": dv["rank_ic_h"], "val_pearson_ic_1": dv["pearson_ic_1"],
            "val_spread_top10_bps": dv["spread_top10_bps"], "val_vol42_exposure": dv["vol42_exposure"],
        })
    out = pd.DataFrame(rows).sort_values("sel_net_taker", ascending=False)
    out.to_csv(OUT_DIR / "summary.csv", index=False)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ML alpha 探索实验")
    parser.add_argument("--cases", default="", help="逗号分隔的 case 名，空 = 全部")
    parser.add_argument("--refresh-panel", action="store_true", help="重新从 ClickHouse 取数（默认用缓存）")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--skip-existing", action="store_true", help="已有 friction_grid.csv 的 case 跳过")
    parser.add_argument("--reeval", action="store_true", help="已有 scores.pkl 的 case 只重新评估（评估网格改了时用），不重训")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args(argv)

    wanted = [c for c in CASES if not args.cases or c.name in args.cases.split(",")]
    if not args.summary_only:
        panel = load_panel(args.refresh_panel)
        print(f"panel：{len(panel.symbols)} 个 symbol × {len(panel.index)} 根 bar", flush=True)
        for case in wanted:
            case_dir = OUT_DIR / case.name
            if args.skip_existing and (case_dir / "friction_grid.csv").exists():
                print(f"[跳过] {case.name}", flush=True)
                continue
            case_dir.mkdir(parents=True, exist_ok=True)
            started = time.monotonic()
            if args.reeval and (case_dir / "scores.pkl").exists():
                evaluate_case(panel, case, pd.read_pickle(case_dir / "scores.pkl"), case_dir, args.workers)
                print(f"[完成] {case.name}：只重新评估 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)
                continue
            if case.source == "official":
                scores = official_scores(panel)
            elif case.source.startswith("factor:"):
                scores = factor_scores(panel, case)
            elif case.source.startswith("blend:"):
                scores = blend_scores(case)
            else:
                scores = train_case(panel, case, case_dir)
            if case.neutralize_scores:
                scores = neutralize_scores(panel, scores, case.neutralize_scores)
            scores.to_pickle(case_dir / "scores.pkl")
            trained = time.monotonic() - started
            evaluate_case(panel, case, scores, case_dir, args.workers)
            print(f"[完成] {case.name}：训练 / 打分 {trained / 60:.1f} 分钟，评估 {(time.monotonic() - started - trained) / 60:.1f} 分钟", flush=True)
    summary = summarize(CASES)
    pd.set_option("display.width", 250)
    print(summary.drop(columns=["note"]).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
