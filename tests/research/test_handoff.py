"""research/ 流水线的交接格式（research/_shared/handoff.py）和关卡2 透传桥接器（factor_synthesis/passthrough.py）。

research/ 不是包，这里按文件路径加载，模块名加前缀，避免跟各关卡目录里同名的 config/data/signals 撞车。
"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

RESEARCH = Path(__file__).resolve().parents[2] / "research"
sys.path.insert(0, str(RESEARCH / "_shared"))

import handoff  # noqa: E402


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


passthrough = _load("research_synthesis_passthrough", RESEARCH / "factor_synthesis" / "passthrough.py")
friction_signals = _load("research_friction_signals", RESEARCH / "friction_test" / "signals.py")


def _entry(name, ic_ir, baseline=None):
    entry = {"name": name, "ic_ir": ic_ir}
    if baseline is not None:
        entry["baseline_ic_ir"] = baseline
    return entry


@pytest.fixture
def candidates():
    return handoff.CandidateSet(
        track="t",
        producer="report",
        regime_sets={
            "trend": {
                "bull": handoff.StateCandidates(factors=[_entry("custom.a", 0.3, 0.2), _entry("custom.b", -0.1, 0.1)]),
                "bear": handoff.StateCandidates(factors=[_entry("custom.b", 0.25, 0.1)], low_sample=True),
                "neutral": handoff.StateCandidates(note="只有 0/2 个因子通过显著性门槛"),
            }
        },
        global_set=handoff.StateCandidates(factors=[_entry("custom.a", 0.2, 0.2)]),
    )


def test_candidate_set_round_trip(tmp_path, candidates):
    path = handoff.write(tmp_path / "report.json", candidates)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["kind"] == "candidates" and raw["schema_version"] == handoff.SCHEMA_VERSION

    loaded = handoff.read_candidates(path, expect_track="t")
    assert loaded.regime_sets["trend"]["bull"].names == ["custom.a", "custom.b"]
    assert loaded.regime_sets["trend"]["bear"].low_sample
    assert loaded.regime_sets["trend"]["neutral"].names == []
    assert loaded.global_set.names == ["custom.a"]
    assert loaded.regime_union() == ["custom.a", "custom.b"]
    assert loaded.all_names() == ["custom.a", "custom.b"]


def test_reading_wrong_kind_or_track_fails(tmp_path, candidates):
    path = handoff.write(tmp_path / "report.json", candidates)
    with pytest.raises(ValueError):
        handoff.read_recipes(path)
    with pytest.raises(SystemExit):
        handoff.read_candidates(path, expect_track="other")
    with pytest.raises(SystemExit):
        handoff.read_candidates(tmp_path / "missing.json")


def test_recipe_validation():
    ok = handoff.RecipeSet(track="t", producer="x", recipes={
        "s": {"kind": "static", "weights": {"custom.a": 1.0}},
        "r": {"kind": "routed", "dimension": "trend", "states": {"bull": {"custom.a": -1.0}}, "fallback": {}},
    })
    assert ok.factor_names() == ["custom.a"]
    ok.to_json()
    for bad in (
        {"kind": "weird", "weights": {}},
        {"kind": "static", "weights": {"custom.a": 0.0}},
        {"kind": "routed", "states": {}, "fallback": {}},
    ):
        with pytest.raises(ValueError):
            handoff.validate_recipe("bad", bad)


def test_sign_of():
    assert handoff.sign_of(0.3) == 1.0 and handoff.sign_of(-2) == -1.0
    assert handoff.sign_of(None) == 0.0 and handoff.sign_of(float("nan")) == 0.0 and handoff.sign_of("x") == 0.0


def test_passthrough_direct_recipes(candidates):
    recipes = passthrough.direct_recipes(candidates, {"singles": True, "equal_weight": True, "routed": True}, track_id="t")
    assert recipes.producer == "synthesis:passthrough"
    r = recipes.recipes
    # 全局方向取 baseline_ic_ir：a +、b +
    # G0 只有 a，跟 single:custom.a 等效，后者被合并进 G0
    assert r["直通·G0 全局等权"] == {"kind": "static", "weights": {"custom.a": 1.0}, "equivalent_to": ["single:custom.a"]}
    assert r["直通·L0 并集等权"] == {"kind": "static", "weights": {"custom.a": 1.0, "custom.b": 1.0}}
    routed = r["直通·L2-trend 路由等权"]
    # state 内方向取该 state 的 ic_ir：bull 里 b 是负的；空名单的 neutral 不出现，退回 fallback = L0
    assert routed["states"] == {"bull": {"custom.a": 1.0, "custom.b": -1.0}, "bear": {"custom.b": 1.0}}
    assert routed["fallback"] == {"custom.a": 1.0, "custom.b": 1.0}
    assert "single:custom.a" not in r
    assert r["single:custom.b"] == {"kind": "static", "weights": {"custom.b": 1.0}}
    assert all("reference" not in recipe for recipe in r.values())
    recipes.to_json()  # 全部配方都能通过格式校验


def test_passthrough_options(candidates):
    only_top_single = passthrough.direct_recipes(candidates, {"singles": 1, "equal_weight": False, "routed": False}, track_id="t")
    assert list(only_top_single.recipes) == ["single:custom.a"]  # |baseline_ic_ir| 最大的那个
    nothing = passthrough.direct_recipes(
        handoff.CandidateSet(track="t", producer="report"), {"singles": True, "equal_weight": True, "routed": True}, track_id="t"
    )
    assert nothing.recipes == {}


def test_passthrough_merges_equivalent_recipes():
    """真实数据里碰到的情况：只有一个因子显著，G0 / L0 / L2 路由 / 单因子参照全都是"只用它"，只该回测一次。"""
    only = handoff.CandidateSet(
        track="t",
        producer="report",
        regime_sets={"trend": {
            "bear": handoff.StateCandidates(factors=[_entry("custom.a", -0.13, -0.13)]),
            "neutral": handoff.StateCandidates(factors=[_entry("custom.a", -0.14, -0.13)]),
            "bull": handoff.StateCandidates(),
        }},
        global_set=handoff.StateCandidates(factors=[_entry("custom.a", -0.13, -0.13)]),
    )
    recipes = passthrough.direct_recipes(only, {"singles": True, "equal_weight": True, "routed": True}, track_id="t")
    assert list(recipes.recipes) == ["直通·G0 全局等权"]
    kept = recipes.recipes["直通·G0 全局等权"]
    assert kept["weights"] == {"custom.a": -1.0}
    assert kept["equivalent_to"] == ["直通·L0 并集等权", "直通·L2-trend 路由等权", "single:custom.a"]
    recipes.to_json()


def test_dedupe_compares_normalized_effective_weights():
    recipes = {
        "a": {"kind": "static", "weights": {"x": 1.0, "y": -1.0}},
        "a_scaled": {"kind": "static", "weights": {"y": -2.0, "x": 2.0}},  # 归一后相同
        "routed_same": {"kind": "routed", "dimension": "trend",
                        "states": {"bull": {"x": 1.0, "y": -1.0}}, "fallback": {"x": 1.0, "y": -1.0}},
        "routed_diff": {"kind": "routed", "dimension": "trend",
                        "states": {"bull": {"x": 1.0}}, "fallback": {"x": 1.0, "y": -1.0}},
        "b": {"kind": "static", "weights": {"x": 1.0, "y": 1.0}},  # 方向不同，不等效
    }
    kept = passthrough.dedupe_recipes(recipes)
    assert list(kept) == ["a", "routed_diff", "b"]
    assert kept["a"]["equivalent_to"] == ["a_scaled", "routed_same"]
    assert "equivalent_to" not in kept["b"]
    assert "equivalent_to" not in recipes["a"]  # 不改输入


def test_routed_recipe_with_empty_fallback_stays_flat_outside_routed_states():
    index = pd.date_range("2026-01-01", periods=4, freq="4h", tz="UTC")
    ranked = {"custom.a": pd.DataFrame({"X": [0.5, -0.5, 0.5, -0.5], "Y": [-0.5, 0.5, -0.5, 0.5]}, index=index)}
    regime = pd.DataFrame({"trend": ["bull", "bear", pd.NA, "bull"]}, index=index)
    recipe = {"kind": "routed", "dimension": "trend", "states": {"bull": {"custom.a": 1.0}}, "fallback": {}}

    scores = friction_signals.case_scores(recipe, ranked, regime)

    bull = (regime["trend"] == "bull").fillna(False).to_numpy()
    pd.testing.assert_frame_equal(scores[bull], ranked["custom.a"][bull])
    assert np.isnan(scores[~bull].to_numpy()).all()
