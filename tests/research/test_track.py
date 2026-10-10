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
