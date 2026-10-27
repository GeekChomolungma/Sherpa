"""模型后端（LightGBM / XGBoost / LSTM）：序列输入、训练配置合并、"训练 -> 清单 -> MLAlpha 推断"整条链。

合成面板和测试用模型跟 `test_ml_training.py` 同一份（下一根收益对这一根有很强的反转），每个后端都应该学到它。
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("lightgbm")

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "ml_training"))

import config as cfg_module  # noqa: E402
from dataset import build_training_frame, plan_folds, split_inner_validation  # noqa: E402
from objective import ICIRObjective, period_starts, tail_weights  # noqa: E402
from trainer import ic_stats, spearman_by_period, train_fold  # noqa: E402

from sherpa.alpha.custom.ml.alpha import MLAlpha  # noqa: E402
from sherpa.alpha.custom.ml.backends import ModelInputs, get_backend  # noqa: E402
from sherpa.alpha.custom.ml.features import FeatureSpec  # noqa: E402
from sherpa.alpha.custom.ml.manifest import Manifest, ModelEntry, fold_dir_name, format_ts, save_manifest  # noqa: E402
from sherpa.alpha.custom.ml.models import LgbmV4  # noqa: E402
from sherpa.alpha.liquidity import LiquidityFilter  # noqa: E402

from .test_ml_training import _reversal_panel  # noqa: E402

TOY_SPEC = FeatureSpec(name="toy", version=1, liquidity=LiquidityFilter(min_percentile=0.5, lookback=20))
LSTM_TOY = {"seq_len": 4, "hidden_size": 8, "max_epochs": 6, "patience": 2, "periods_per_batch": 16,
            "learning_rate": 5e-3, "num_threads": 1}
XGB_TOY = {"eta": 0.1, "max_leaves": 7, "min_child_weight": 50.0, "nthread": 1}


class _ToyXgb(MLAlpha):
    name = "ml_toy_xgb"
    model_name = "toy_xgb"
    spec = TOY_SPEC
    training_overrides = {"backend": "xgboost", "backend_params": XGB_TOY}


class _ToyLstm(MLAlpha):
    """不写 device = 默认 GPU。"""

    name = "ml_toy_lstm"
    model_name = "toy_lstm"
    spec = TOY_SPEC
    training_overrides = {"backend": "lstm", "backend_params": LSTM_TOY}


class _ToyLstmCpu(MLAlpha):
    name = "ml_toy_lstm_cpu"
    model_name = "toy_lstm_cpu"
    spec = TOY_SPEC
    training_overrides = {"backend": "lstm", "backend_params": {**LSTM_TOY, "device": "cpu"}}


def _needs(alpha_cls):
    """跳过当前机器跑不了的后端：XGBoost 没装、torch 没装、默认 GPU 的 LSTM 没有可用 GPU。"""
    if alpha_cls is _ToyXgb:
        pytest.importorskip("xgboost")
        return
    torch = pytest.importorskip("torch")
    if alpha_cls is _ToyLstm and not torch.cuda.is_available():
        pytest.skip("没有可用的 CUDA 设备")


ALL_TOYS = pytest.mark.parametrize("alpha_cls", [_ToyXgb, _ToyLstm, _ToyLstmCpu], ids=["xgboost", "lstm-cuda", "lstm-cpu"])


def _train(panel, root: Path, alpha_cls, *, seeds=(0,)) -> Manifest:
    cfg = cfg_module.for_model(alpha_cls.training_overrides)
    frame = build_training_frame(panel, alpha_cls.spec, horizon=1, delay=0, neutralize_label=False,
                                 tail_quantile=0.2, tail_weight=3.0)
    folds = plan_folds(research_start=panel.index[0], last_bar=panel.index[-1], interval="4h",
                       retrain_every_bars=120, min_train_bars=360, purge_bars=1, train_window_bars=300)
    model_dir = root / alpha_cls.model_name
    manifest = Manifest(model=alpha_cls.model_name, feature_fingerprint=alpha_cls.spec.fingerprint,
                        feature_names=list(alpha_cls.spec.feature_names), config_fingerprint="test",
                        config=cfg.to_dict())
    for fold in folds:
        rows = frame.rows_between(fold.train_from, fold.train_until)
        fit, valid = split_inner_validation(frame, rows, train_until=fold.train_until, valid_bars=60, purge_bars=1,
                                            interval="4h")
        rel = fold_dir_name(fold.valid_from)
        result = train_fold(
            frame, fit, valid, model_dir / rel, full=rows, objective="ic_ir", seeds=seeds, lgb_params={},
            num_boost_round=60, early_stopping_rounds=20, min_period_rows=5, rel_prefix=rel,
            backend=cfg.backend, backend_params=cfg.backend_params,
        )
        manifest.entries.append(ModelEntry(
            valid_from=format_ts(fold.valid_from), valid_until=format_ts(fold.valid_until),
            train_rows_until=format_ts(fold.train_until), files=result.files, best_iterations=result.best_iterations,
        ))
    save_manifest(model_dir, manifest)
    return manifest


def _oos_rank_ic(panel, scores: pd.DataFrame) -> float:
    label = panel.close.pct_change(fill_method=None).shift(-1)
    stacked = pd.DataFrame({"p": scores.stack(), "y": label.stack()}).dropna()
    times = pd.DatetimeIndex(stacked.index.get_level_values(0))
    return ic_stats(spearman_by_period(stacked["p"].to_numpy(), stacked["y"].to_numpy(), times, min_period_rows=5))[
        "rank_ic_mean"]


# ---------------------------------------------------------------------------
# 序列输入
# ---------------------------------------------------------------------------

def _inputs():
    """3 根 bar × 2 个币；B 在第 0 根还没上线（没有特征行）。"""
    index = pd.MultiIndex.from_tuples(
        [(0, "A"), (1, "A"), (1, "B"), (2, "A"), (2, "B")], names=["start_time", "symbol"])
    features = pd.DataFrame({"f": [1.0, 2.0, 20.0, 3.0, 30.0]}, index=index)
    return ModelInputs.from_features(features, pd.Index([0, 1, 2]), pd.Index(["A", "B"]))


def test_sequences_look_back_along_the_same_symbol_and_end_at_the_current_row():
    inputs = _inputs()
    x, present = inputs.sequences(np.array([3, 4, 0]), 3)  # (2, A)、(2, B)、(0, A)
    assert x.shape == (3, 3, 1)
    np.testing.assert_array_equal(x[0, :, 0], [1.0, 2.0, 3.0])
    np.testing.assert_array_equal(present[1], [False, True, True])
    assert np.isnan(x[1, 0, 0]) and list(x[1, 1:, 0]) == [20.0, 30.0]
    np.testing.assert_array_equal(present[2], [False, False, True])  # 序列开头之前也是"不存在"
    assert x[2, -1, 0] == 1.0


def test_sequence_length_one_is_the_tabular_row():
    inputs = _inputs()
    rows = np.arange(5)
    x, present = inputs.sequences(rows, 1)
    np.testing.assert_array_equal(x[:, 0, :], inputs.rows(rows))
    assert present.all()


# ---------------------------------------------------------------------------
# 训练配置
# ---------------------------------------------------------------------------

def test_lightgbm_config_payload_has_no_backend_keys_so_old_fingerprints_hold():
    cfg = cfg_module.for_model(LgbmV4.training_overrides)
    assert cfg.backend == "lightgbm"
    assert "backend" not in cfg.to_dict() and "backend_params" not in cfg.to_dict()
    assert "lgb_params" in cfg.to_dict()


def test_other_backends_merge_their_defaults_and_drop_lgb_params():
    cfg = cfg_module.for_model({"backend": "xgboost", "backend_params": {"eta": 0.01}})
    payload = cfg.to_dict()
    assert payload["backend"] == "xgboost" and "lgb_params" not in payload
    assert payload["backend_params"] == {**cfg_module.XGB_PARAMS, "eta": 0.01}


def test_backend_params_are_validated():
    with pytest.raises(ValueError, match="seq_len"):
        cfg_module.for_model({"backend": "lstm"})
    with pytest.raises(ValueError, match="不认识的键"):
        cfg_module.for_model({"backend": "xgboost", "backend_params": {"etaa": 0.1}})
    with pytest.raises(ValueError, match="lgb_params"):
        cfg_module.for_model({"backend_params": {"num_leaves": 7}})
    with pytest.raises(ValueError, match="未知的 backend"):
        cfg_module.for_model({"backend": "catboost"})


def test_sequence_backend_extends_min_lookback():
    assert _ToyLstm().min_lookback == TOY_SPEC.min_lookback + LSTM_TOY["seq_len"] - 1
    assert _ToyXgb().min_lookback == TOY_SPEC.min_lookback


def test_model_case_carries_the_backend_of_the_bound_model():
    import run_experiments

    case = run_experiments.model_case("x", "x", "LgbmV4")
    assert case.backend == "lightgbm" and case.train_config.backend_params == {}


# ---------------------------------------------------------------------------
# 训练 -> 清单 -> 推断
# ---------------------------------------------------------------------------

@ALL_TOYS
def test_backend_trains_scores_out_of_sample_and_is_point_in_time(alpha_cls, tmp_path, monkeypatch):
    _needs(alpha_cls)
    panel = _reversal_panel()
    manifest = _train(panel, tmp_path, alpha_cls)
    assert manifest.backend == alpha_cls.training_overrides["backend"]
    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))

    scores = alpha_cls().compute(panel)
    first = manifest.sorted_entries()[0].valid_from_ts
    assert scores.loc[scores.index < first].isna().all().all()
    scope = alpha_cls.spec.liquidity.mask(panel).loc[scores.index >= first]
    assert scores.loc[scores.index >= first].notna().equals(scope)
    assert _oos_rank_ic(panel, scores) > 0.1  # 学到了反转

    cut = alpha_cls().compute(panel.slice(slice(0, 560)))
    pd.testing.assert_frame_equal(cut, scores.iloc[:560])


def test_manifest_backend_must_match_the_model_class(tmp_path, monkeypatch):
    pytest.importorskip("xgboost")
    panel = _reversal_panel(n=500)
    _train(panel, tmp_path, _ToyXgb)
    raw = json.loads((tmp_path / "toy_xgb" / "manifest.json").read_text(encoding="utf-8"))
    raw["config"]["backend"] = "lightgbm"
    (tmp_path / "toy_xgb" / "manifest.json").write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))
    with pytest.raises(ValueError, match="后端"):
        _ToyXgb().compute(panel)


@ALL_TOYS
def test_a_seed_trains_the_same_model_regardless_of_which_seeds_ran_before_it(alpha_cls, tmp_path):
    _needs(alpha_cls)
    panel = _reversal_panel(n=500)
    _train(panel, tmp_path / "alone", alpha_cls, seeds=(5,))
    _train(panel, tmp_path / "after", alpha_cls, seeds=(0, 5))
    backend = get_backend(alpha_cls.training_overrides["backend"])
    frame = build_training_frame(panel, alpha_cls.spec, horizon=1, delay=0, neutralize_label=False,
                                 tail_quantile=0.2, tail_weight=3.0)
    rows = np.arange(len(frame.source_rows))[-200:]
    fold = sorted(p.name for p in (tmp_path / "alone" / alpha_cls.model_name).iterdir() if p.is_dir())[0]
    a, b = (
        backend.predict(backend.load(tmp_path / which / alpha_cls.model_name / fold / f"seed5{backend.suffix}"),
                        frame.inputs, frame.source_rows[rows])
        for which in ("alone", "after")
    )
    np.testing.assert_allclose(a, b)


def test_lstm_batch_loss_is_the_same_ic_ir_as_the_tree_objective():
    torch = pytest.importorskip("torch")
    from trainers.lstm import ic_ir_loss

    rng = np.random.default_rng(0)
    times = np.repeat(np.arange(5), [12, 9, 15, 11, 10])
    y = rng.normal(size=len(times))
    w = tail_weights(rng.uniform(-0.5, 0.5, len(times)), tail_quantile=0.2, tail_weight=3.0)
    p = 0.4 * y + rng.normal(size=len(times))
    expected = ICIRObjective(y, w, period_starts(times), min_period_rows=1).ic_ir(p)
    loss = ic_ir_loss(torch.tensor(p), torch.tensor(y), torch.tensor(w), torch.tensor(times), 5)
    assert -loss.item() == pytest.approx(expected, rel=1e-4)


# ---------------------------------------------------------------------------
# LSTM 的设备：默认 GPU，显式 cpu 才用 CPU，要 GPU 没有 GPU 直接报错
# ---------------------------------------------------------------------------

def test_lstm_device_defaults_to_cuda_and_is_validated():
    assert cfg_module.for_model({"backend": "lstm", "backend_params": {"seq_len": 6}}).backend_params["device"] == "cuda"
    cpu = cfg_module.for_model({"backend": "lstm", "backend_params": {"seq_len": 6, "device": "cpu"}})
    assert cpu.backend_params["device"] == "cpu"
    with pytest.raises(ValueError, match="device"):
        cfg_module.for_model({"backend": "lstm", "backend_params": {"seq_len": 6, "device": "gpu"}})


def test_training_on_cuda_without_a_gpu_fails_instead_of_falling_back(monkeypatch):
    torch = pytest.importorskip("torch")
    from sherpa.alpha.custom.ml.backends import lstm as lstm_backend

    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    with pytest.raises(RuntimeError, match="device='cpu'"):
        lstm_backend.resolve_device("cuda")
    assert lstm_backend.resolve_device("cpu").type == "cpu"


def test_gpu_trained_checkpoint_records_its_device_and_loads_on_cpu(tmp_path, monkeypatch):
    torch = pytest.importorskip("torch")
    if not torch.cuda.is_available():
        pytest.skip("没有可用的 CUDA 设备")
    from sherpa.alpha.custom.ml.backends import lstm as lstm_backend

    panel = _reversal_panel(n=500)
    _train(panel, tmp_path, _ToyLstm)
    path = next((tmp_path / "toy_lstm").rglob("seed0.pt"))
    model = lstm_backend.load_checkpoint(path)
    assert model.train_device == "cuda" and model.device.type == "cuda"
    monkeypatch.setenv("SHERPA_TORCH_DEVICE", "cpu")
    on_cpu = lstm_backend.load_checkpoint(path)
    assert on_cpu.device.type == "cpu"
    frame = build_training_frame(panel, TOY_SPEC, horizon=1, delay=0, neutralize_label=False, tail_quantile=0.2, tail_weight=3.0)
    rows = frame.source_rows[-300:]
    backend = get_backend("lstm")
    np.testing.assert_allclose(backend.predict(model, frame.inputs, rows), backend.predict(on_cpu, frame.inputs, rows), atol=1e-4)
