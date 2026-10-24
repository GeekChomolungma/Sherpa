"""research/_shared/track.py：研究线配置的 `alphas.include` 白名单。"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "research" / "_shared"))

from track import load_track  # noqa: E402

ML_MODULE = "sherpa.alpha.custom.ml.models"


def _write_track(tmp_path: Path, alphas: dict) -> Path:
    track_dir = tmp_path / "t"
    track_dir.mkdir()
    (track_dir / "track.json").write_text(json.dumps({"id": "t", "alphas": alphas}), encoding="utf-8")
    return track_dir


def test_select_alphas_without_include_takes_whole_module(tmp_path):
    track = load_track(_write_track(tmp_path, {"modules": [ML_MODULE], "family": "custom"}))
    assert {"custom.ml_lgbm_v1", "custom.ml_lgbm_v2", "custom.ml_lgbm_v3"} <= set(track.select_alphas())


def test_select_alphas_include_keeps_only_listed(tmp_path):
    track = load_track(_write_track(
        tmp_path, {"modules": [ML_MODULE], "family": "custom", "include": ["custom.ml_lgbm_v3"]}
    ))
    assert track.select_alphas() == ["custom.ml_lgbm_v3"]


def test_select_alphas_include_rejects_names_outside_modules(tmp_path):
    track = load_track(_write_track(
        tmp_path, {"modules": [ML_MODULE], "family": "custom", "include": ["worldquant.alpha001"]}
    ))
    with pytest.raises(SystemExit, match="alphas.include"):
        track.select_alphas()


# ---------------------------------------------------------------------------
# 按 run 归档（outputs.per_run）：不同模型 / 变体的产出互不覆盖
# ---------------------------------------------------------------------------

def _per_run_track(tmp_path: Path, include=("custom.ml_lgbm_v4",), per_run=True) -> Path:
    track_dir = tmp_path / "t"
    track_dir.mkdir()
    raw = {"id": "t", "alphas": {"modules": [ML_MODULE], "family": "custom", "include": list(include)},
           "preprocess": {"neutralize": False}}
    if per_run:
        raw["outputs"] = {"per_run": True}
    (track_dir / "track.json").write_text(json.dumps(raw), encoding="utf-8")
    return track_dir


def test_per_run_outputs_are_named_after_the_model(tmp_path, monkeypatch):
    monkeypatch.delenv("SHERPA_TRACK_ALPHAS", raising=False)
    monkeypatch.delenv("SHERPA_RUN_VARIANT", raising=False)
    track = load_track(_per_run_track(tmp_path))
    assert track.run_id == "lgbm_v4"  # = MLAlpha.model_name，跟 models/lgbm_v4/ 对齐
    run_dir = track.dir / "runs" / "lgbm_v4"
    assert track.profile_path == run_dir / "regime_alpha_profile_without_neutralization.csv"
    assert track.results_dir == run_dir / "results_without_neutralization"
    assert track.handoff_path("synthesis") == run_dir / "handoff_without_neutralization" / "synthesis.json"


def test_alphas_override_and_variant_pick_a_separate_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SHERPA_TRACK_ALPHAS", "custom.ml_lgbm_v2, custom.ml_lgbm_v3")
    monkeypatch.setenv("SHERPA_RUN_VARIANT", "start2024")
    track = load_track(_per_run_track(tmp_path))
    assert track.select_alphas() == ["custom.ml_lgbm_v2", "custom.ml_lgbm_v3"]
    assert track.run_id == "lgbm_v2+lgbm_v3__start2024"
    assert track.output_dir == track.dir / "runs" / "lgbm_v2+lgbm_v3__start2024"


def test_tracks_without_per_run_keep_the_flat_layout_and_reject_variants(tmp_path, monkeypatch):
    monkeypatch.delenv("SHERPA_RUN_VARIANT", raising=False)
    track = load_track(_per_run_track(tmp_path, per_run=False))
    assert track.run_id == "" and track.output_dir == track.dir
    assert track.results_dir == track.dir / "results_without_neutralization"
    monkeypatch.setenv("SHERPA_RUN_VARIANT", "start2024")
    with pytest.raises(SystemExit, match="per_run"):
        load_track(track.dir)


def test_variant_also_separates_ml_model_files(tmp_path, monkeypatch):
    from sherpa.alpha.custom.ml import LgbmV4

    monkeypatch.setenv("SHERPA_ML_MODEL_ROOT", str(tmp_path))
    monkeypatch.delenv("SHERPA_RUN_VARIANT", raising=False)
    assert LgbmV4().model_dir == tmp_path / "lgbm_v4"
    monkeypatch.setenv("SHERPA_RUN_VARIANT", "start2024")
    assert LgbmV4().model_dir == tmp_path / "lgbm_v4__start2024"


def test_mlalpha_track_archives_per_run():
    track = load_track("MLalpha")
    assert track.per_run
