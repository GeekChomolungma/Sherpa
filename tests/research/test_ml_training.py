"""research/ml_training：IC_IR 损失、训练集 / 滚动时间表、以及"训练 -> 模型清单 -> MLAlpha 推断"整条链。

research/ 不是包；ml_training 里的模块互相按裸名 import（objective / dataset / trainer），这里把目录插进 sys.path。
不 import 它的 config.py / data.py（跟其它关卡目录里的同名模块会撞车，也不需要）。
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "ml_training"))

from dataset import build_training_frame, liquidity_from_tradable, plan_folds, split_inner_validation  # noqa: E402
from objective import ICIRObjective, period_starts, tail_weights  # noqa: E402
from trainer import ic_stats, spearman_by_period, train_fold  # noqa: E402

from sherpa.alpha.custom.ml import LgbmV1  # noqa: E402
from sherpa.alpha.custom.ml.alpha import MLAlpha  # noqa: E402
from sherpa.alpha.custom.ml.features import FeatureSpec  # noqa: E402
from sherpa.alpha.custom.ml.manifest import Manifest, ModelEntry, fold_dir_name, format_ts, save_manifest  # noqa: E402
from sherpa.alpha.liquidity import LiquidityFilter  # noqa: E402
from sherpa.data.schema import BarPanel, build_coverage  # noqa: E402
from sherpa.metrics.tradability import tradable_mask  # noqa: E402


# ---------------------------------------------------------------------------
# 损失
# ---------------------------------------------------------------------------

def _objective(seed=0):
    rng = np.random.default_rng(seed)
    times = np.repeat(np.arange(6), [12, 15, 11, 20, 13, 14])
    y = rng.normal(size=len(times))
    w = tail_weights(rng.uniform(-0.5, 0.5, len(times)), tail_quantile=0.2, tail_weight=3.0)
    return ICIRObjective(y, w, period_starts(times), min_period_rows=5), y, rng


def test_ic_ir_gradient_matches_finite_differences():
    obj, y, rng = _objective()
    p = 0.3 * y + rng.normal(size=len(y))
    grad = obj.gradient(p)
    h = 1e-6
    numeric = np.array([
        (-obj.ic_ir(p + h * e) + obj.ic_ir(p - h * e)) / (2 * h) for e in np.eye(len(p))
    ])
    np.testing.assert_allclose(grad, numeric, atol=1e-7)


def test_first_step_from_constant_prediction_points_towards_label():
    obj, y, _ = _objective()
    grad, hess = obj.lgb_objective(np.zeros(len(y)), None)
    assert np.corrcoef(-grad, y)[0, 1] > 0.8
    assert np.isclose(np.sqrt(np.mean(grad**2)), 1.0) and (hess == 1).all()


def test_ic_is_scale_and_shift_invariant_per_period():
    obj, y, rng = _objective()
    p = y + rng.normal(size=len(y))
    np.testing.assert_allclose(obj.ic_series(p), obj.ic_series(3 * p + 7))


def test_tail_weights_mark_both_ends():
    w = tail_weights(np.array([-0.5, -0.31, -0.29, 0.0, 0.29, 0.31, 0.5]), tail_quantile=0.2, tail_weight=3.0)
    assert w.tolist() == [3.0, 3.0, 1.0, 1.0, 1.0, 3.0, 3.0]


# ---------------------------------------------------------------------------
# 滚动时间表
# ---------------------------------------------------------------------------

def test_plan_folds_is_anchored_on_research_start_and_purged():
    start = pd.Timestamp("2022-01-01", tz="UTC")
    kwargs = dict(research_start=start, interval="4h", retrain_every_bars=120, min_train_bars=1080, purge_bars=2)
    short = plan_folds(last_bar=start + pd.Timedelta(days=260), **kwargs)
    longer = plan_folds(last_bar=start + pd.Timedelta(days=400), **kwargs)
    assert short[0].valid_from == start + pd.Timedelta(days=180)
    assert short[0].train_until == short[0].valid_from - pd.Timedelta(hours=8)
    assert all(b.valid_from == a.valid_until for a, b in zip(longer, longer[1:]))
    assert longer[: len(short)] == short  # 数据变长只追加重训时点，前面的不变
    assert all(f.train_from is None for f in short)
    window = plan_folds(last_bar=start + pd.Timedelta(days=260), train_window_bars=600, **kwargs)
    assert window[0].train_from == window[0].valid_from - pd.Timedelta(days=100)


# ---------------------------------------------------------------------------
# 训练 -> 清单 -> 推断
# ---------------------------------------------------------------------------

def _reversal_panel(n=700, n_symbols=30, seed=0) -> BarPanel:
    """下一根收益 = −0.4 × 这一根收益 + 噪声：ret_1 特征对标签（horizon=1, delay=0）有很强的反向预测力。"""
    rng = np.random.default_rng(seed)
    symbols = ["BTCUSDT"] + [f"S{i:02d}USDT" for i in range(n_symbols - 1)]
    index = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC", name="start_time")
    r = np.zeros((n, n_symbols))
    market = rng.normal(0, 0.01, n)
    for t in range(1, n):
        r[t] = -0.4 * r[t - 1] + market[t] + rng.normal(0, 0.02, n_symbols)
    close = pd.DataFrame(100 * np.exp(np.cumsum(r, axis=0)), index=index, columns=symbols)
    volume = pd.DataFrame(rng.uniform(100, 1000, (n, n_symbols)), index=index, columns=symbols)
    fields = dict(
        open=close.shift(1).fillna(close), high=close * 1.01, low=close * 0.99, close=close, volume=volume,
        quote_volume=volume * close, taker_buy_volume=volume * 0.5, taker_buy_quote_volume=volume * close * 0.5,
        trades_count=volume.round(),
    )
    return BarPanel(interval="4h", symbols=tuple(symbols), coverage=build_coverage(close, n_symbols), **fields)


class _ToyML(MLAlpha):
    """测试用：只有 A、C 组特征（不带世坤因子），流动性范围 = 成交额截面前一半，不注册。"""

    name = "ml_toy"
    model_name = "toy"
    spec = FeatureSpec(name="toy", version=1, liquidity=LiquidityFilter(min_percentile=0.5, lookback=20))


def _train_toy(panel, root: Path) -> Manifest:
    frame = build_training_frame(
        panel, _ToyML.spec, horizon=1, delay=0, neutralize_label=False, tail_quantile=0.2, tail_weight=3.0
    )
    folds = plan_folds(
        research_start=panel.index[0], last_bar=panel.index[-1], interval="4h",
        retrain_every_bars=120, min_train_bars=360, purge_bars=1, train_window_bars=300,
    )
    model_dir = root / _ToyML.model_name
    manifest = Manifest(model="toy", feature_fingerprint=_ToyML.spec.fingerprint,
                        feature_names=list(_ToyML.spec.feature_names), config_fingerprint="test")
    for fold in folds:
        rows = frame.rows_between(fold.train_from, fold.train_until)
        assert frame.times[rows.stop - 1] <= fold.train_until
        fit, valid = split_inner_validation(
            frame, rows, train_until=fold.train_until, valid_bars=60, purge_bars=1, interval="4h"
        )
        assert frame.times[fit.stop - 1] < frame.times[valid.start] - pd.Timedelta(hours=4)  # 中间隔了 purge
        rel = fold_dir_name(fold.valid_from)
        result = train_fold(
            frame, fit, valid, model_dir / rel, full=rows, objective="ic_ir", seeds=(0,),
            lgb_params={"learning_rate": 0.1, "num_leaves": 7, "min_data_in_leaf": 50, "verbose": -1, "num_threads": 1},
            num_boost_round=60, early_stopping_rounds=20, min_period_rows=5, rel_prefix=rel,
        )
        manifest.entries.append(ModelEntry(
            valid_from=format_ts(fold.valid_from), valid_until=format_ts(fold.valid_until),
            train_rows_until=format_ts(fold.train_until), files=result.files, best_iterations=result.best_iterations,
        ))
    save_manifest(model_dir, manifest)
    return manifest


def test_training_to_inference_end_to_end(tmp_path, monkeypatch):
    panel = _reversal_panel()
    manifest = _train_toy(panel, tmp_path)
    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))
    alpha = _ToyML()
    scores = alpha.compute(panel)

    first = manifest.sorted_entries()[0].valid_from_ts
    assert scores.shape == panel.close.shape
    assert scores.loc[scores.index < first].isna().all().all()  # 第一个模型之前没有打分
    # 之后只在流动性范围内打分，范围外是 NaN
    scope = _ToyML.spec.liquidity.mask(panel).loc[scores.index >= first]
    after = scores.loc[scores.index >= first]
    assert after.notna().equals(scope)
    assert not scope.all().all()  # 范围真的排除了一些格子，上面的断言才有意义

    # 模型学到了反转：样本外打分和下一根收益正相关
    label = panel.close.pct_change(fill_method=None).shift(-1)
    stacked = pd.DataFrame({"p": scores.stack(), "y": label.stack()}).dropna()
    times = pd.DatetimeIndex(stacked.index.get_level_values(0))
    stats = ic_stats(spearman_by_period(stacked["p"].to_numpy(), stacked["y"].to_numpy(), times, min_period_rows=5))
    assert stats["rank_ic_mean"] > 0.1


def test_ml_alpha_scores_are_point_in_time(tmp_path, monkeypatch):
    """截断面板算出来的打分，跟完整面板算出来的对应行完全一致（阶段一 / 关卡3 取的数据长度不同，靠的就是这点）。"""
    panel = _reversal_panel()
    _train_toy(panel, tmp_path)
    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))
    full = _ToyML().compute(panel)
    k = 560
    cut = _ToyML().compute(panel.slice(slice(0, k)))
    pd.testing.assert_frame_equal(cut, full.iloc[:k])


# ---------------------------------------------------------------------------
# 流动性范围：模型 spec 和研究线评估掩码一致
# ---------------------------------------------------------------------------

def test_liquidity_from_tradable_fills_tradable_mask_defaults():
    defaults = liquidity_from_tradable(True)
    assert defaults.min_percentile == 0.40 and defaults.min_quote_volume > 0 and defaults.seasoning_period == 20
    override = liquidity_from_tradable({"min_percentile": 0.5, "min_quote_volume": 0, "min_trades_count": 0})
    assert override == LiquidityFilter(min_percentile=0.5, seasoning_period=20, lookback=120)
    assert liquidity_from_tradable(False) == LiquidityFilter()


def test_liquidity_filter_mask_matches_tradable_mask_with_same_params():
    """换算出来的 LiquidityFilter 算的掩码，跟研究流水线用 tradable_mask 算的是同一张表。"""
    panel = _reversal_panel(n=200)
    params = {"min_percentile": 0.5, "min_quote_volume": 0, "min_trades_count": 0}
    expected = tradable_mask(panel.quote_volume, panel.trades_count, **params)
    pd.testing.assert_frame_equal(liquidity_from_tradable(params).mask(panel), expected)


def test_mlalpha_track_matches_lgbm_v1_spec():
    """MLalpha 研究线 track.json 的评估掩码跟 LgbmV1 的流动性范围一致（训练脚本开头也会校验，这里提前在单测里拦住）。"""
    import json

    track = json.loads((Path(__file__).resolve().parents[2] / "research" / "alpha_research" / "MLalpha" / "track.json")
                       .read_text(encoding="utf-8"))
    assert liquidity_from_tradable(track["preprocess"]["tradable_mask"]) == LgbmV1.spec.liquidity


# ---------------------------------------------------------------------------
# 滑动窗口 + 两步训练（早停 → 整窗重训）
# ---------------------------------------------------------------------------

def _toy_frame():
    panel = _reversal_panel()
    frame = build_training_frame(
        panel, _ToyML.spec, horizon=1, delay=0, neutralize_label=False, tail_quantile=0.2, tail_weight=3.0
    )
    return panel, frame


def test_inner_validation_is_the_latest_fixed_number_of_bars():
    panel, frame = _toy_frame()
    fold = plan_folds(
        research_start=panel.index[0], last_bar=panel.index[-1], interval="4h",
        retrain_every_bars=120, min_train_bars=480, purge_bars=2, train_window_bars=360,
    )[0]
    rows = frame.rows_between(fold.train_from, fold.train_until)
    assert frame.times[rows.start] >= fold.train_from  # 滑动窗口：起点跟着 τ 走，不是从头开始
    fit, valid = split_inner_validation(frame, rows, train_until=fold.train_until, valid_bars=120, purge_bars=2, interval="4h")
    valid_times = frame.times[valid].unique()
    assert len(valid_times) == 120 and valid_times[-1] == fold.train_until  # 验证段 = 窗口里最近 120 根
    gap = valid_times[0] - frame.times[fit.stop - 1]
    assert gap == pd.Timedelta(hours=4 * 3)  # 拟合段最后一根和验证段第一根之间空出 purge = 2 根
    assert fit.start == rows.start and valid.stop == rows.stop


def test_refit_trains_final_model_on_the_full_window_with_the_early_stopped_rounds(tmp_path):
    panel, frame = _toy_frame()
    fold = plan_folds(
        research_start=panel.index[0], last_bar=panel.index[-1], interval="4h",
        retrain_every_bars=120, min_train_bars=480, purge_bars=1, train_window_bars=360,
    )[0]
    rows = frame.rows_between(fold.train_from, fold.train_until)
    fit, valid = split_inner_validation(frame, rows, train_until=fold.train_until, valid_bars=120, purge_bars=1, interval="4h")
    params = {"learning_rate": 0.1, "num_leaves": 7, "min_data_in_leaf": 50, "verbose": -1, "num_threads": 1}
    common = dict(objective="ic_ir", seeds=(0,), lgb_params=params, num_boost_round=60, early_stopping_rounds=20,
                  min_period_rows=5, rel_prefix="x")

    refit = train_fold(frame, fit, valid, tmp_path / "refit", full=rows, **common)
    stopped = train_fold(frame, fit, valid, tmp_path / "stopped", full=None, **common)

    import lightgbm as lgb

    model = lgb.Booster(model_file=str(tmp_path / "refit" / "seed0.txt"))
    assert refit.best_iterations == stopped.best_iterations  # 轮数由第①步早停决定，两种方式一样
    assert model.num_trees() == refit.best_iterations[0]     # 第②步按这个轮数重训
    assert refit.metrics["n_refit_rows"] == rows.stop - rows.start > refit.metrics["n_fit_rows"]
    # 重训用了更多数据（含验证段），模型确实变了
    x = frame.features[valid]
    other = lgb.Booster(model_file=str(tmp_path / "stopped" / "seed0.txt"))
    assert not np.allclose(model.predict(x), other.predict(x))
