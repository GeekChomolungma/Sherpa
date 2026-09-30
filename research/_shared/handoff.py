"""流水线各阶段之间的交接格式（handoff）：生产者有义务按这里的格式输出，消费者只认这个格式。

以前各关卡靠"下游 refresh 脚本读上游的明细 CSV、重写自己的 config.py"串起来：下游要懂上游 CSV 的列，
refresh 之间顺序嵌套，跳过某一关就得给下游另写一套读法。现在反过来——**每个阶段自己负责把产出写成标准
交接文件**，下一阶段只读交接文件，不关心它是谁、用什么方法产出的。某条研究线不需要某一关时，那一关以
"透传"模式运行，同样产出一份标准交接文件，下游感知不到差别。

整条流水线只有两种交接物：

- **候选集** `CandidateSet`（kind = "candidates"）：`{维度: {state: 因子列表}}` + 一份不分 regime 的全局
  名单。汇总报告（04/05 矩阵）产出它；关卡1 吃它、再产出一份去冗余后的它（关卡1 本质是候选集过滤器）；
  关卡2 吃它。
- **配方集** `RecipeSet`（kind = "recipes"）：一组冻结配方，每个配方要么是 static（全程一组带符号权重），
  要么是 routed（按某个 regime 维度的 state 切换权重，state 未知时用 fallback）。关卡2 产出它，关卡3 吃它。

阶段顺序固定：report → orthogonalization → synthesis → friction，每个阶段读前一个阶段的交接文件
（`INPUT_STAGE`），写 `<研究线>/handoff/<阶段>.json`。交接文件是 JSON，人可以直接改（比如手动删掉某个
候选因子），改完从下一阶段开始重跑即可。

因子条目是 `{"name": qualified_name, ...元信息}`。元信息只给人看、或给下游做参考（比如 `ic_ir` 的符号可以
当方向），下游不能依赖某个元信息字段一定存在——除了 `name`。常见字段：
`ic_ir`（该 state 切片内的 IC_IR，带方向）、`t_stat`、`baseline_ic_ir`（全历史 IC_IR）、`low_sample`、
`absorbed`（关卡1：这个代表因子吸收掉的冗余因子）。

这是 research 子项目之间唯二共享的东西之一（另一个是 `research_config.json`）：共享的是格式定义，不是业务逻辑。
只依赖标准库，任何阶段都能 import。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

SCHEMA_VERSION = 1

# 产出交接文件的阶段 -> 交接物种类；以及每个阶段读谁的交接文件。
STAGE_KIND: dict[str, str] = {
    "report": "candidates",
    "orthogonalization": "candidates",
    "synthesis": "recipes",
}
INPUT_STAGE: dict[str, str] = {
    "orthogonalization": "report",
    "synthesis": "orthogonalization",
    "friction": "synthesis",
}


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# 候选集
# ---------------------------------------------------------------------------


@dataclass
class StateCandidates:
    """一个 (dimension, state) 切片（或全局）的候选因子：顺序有意义（强的在前）。"""

    factors: list[dict[str, Any]] = field(default_factory=list)
    low_sample: bool = False
    note: str = ""

    @property
    def names(self) -> list[str]:
        return [f["name"] for f in self.factors]

    def to_json(self) -> dict[str, Any]:
        return {"low_sample": self.low_sample, "note": self.note, "factors": self.factors}

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "StateCandidates":
        factors = [dict(f) for f in raw.get("factors", [])]
        for f in factors:
            if not isinstance(f.get("name"), str) or not f["name"]:
                raise ValueError(f"候选因子条目缺少 name：{f}")
        return cls(factors=factors, low_sample=bool(raw.get("low_sample", False)), note=str(raw.get("note", "")))


@dataclass
class CandidateSet:
    track: str
    producer: str
    regime_sets: dict[str, dict[str, StateCandidates]] = field(default_factory=dict)
    global_set: StateCandidates = field(default_factory=StateCandidates)
    meta: dict[str, Any] = field(default_factory=dict)

    kind = "candidates"

    @property
    def dimensions(self) -> list[str]:
        return list(self.regime_sets)

    def regime_union(self) -> list[str]:
        """各 state 名单的并集，按首次出现顺序去重。"""
        seen: dict[str, None] = {}
        for states in self.regime_sets.values():
            for cands in states.values():
                for name in cands.names:
                    seen.setdefault(name, None)
        return list(seen)

    def all_names(self) -> list[str]:
        return list(dict.fromkeys(self.regime_union() + self.global_set.names))

    def factor_entries(self) -> dict[str, dict[str, Any]]:
        """name -> 该因子第一次出现的条目（全局名单优先），给需要元信息兜底的下游用。"""
        entries: dict[str, dict[str, Any]] = {}
        for f in self.global_set.factors:
            entries.setdefault(f["name"], f)
        for states in self.regime_sets.values():
            for cands in states.values():
                for f in cands.factors:
                    entries.setdefault(f["name"], f)
        return entries

    def to_json(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "track": self.track,
            "producer": self.producer,
            "created_at": _now(),
            "meta": self.meta,
            "regime_sets": {
                dim: {state: cands.to_json() for state, cands in states.items()}
                for dim, states in self.regime_sets.items()
            },
            "global": self.global_set.to_json(),
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "CandidateSet":
        _check_header(raw, "candidates")
        return cls(
            track=raw["track"],
            producer=raw["producer"],
            regime_sets={
                dim: {state: StateCandidates.from_json(c) for state, c in states.items()}
                for dim, states in raw.get("regime_sets", {}).items()
            },
            global_set=StateCandidates.from_json(raw.get("global", {})),
            meta=dict(raw.get("meta", {})),
        )


# ---------------------------------------------------------------------------
# 配方集
# ---------------------------------------------------------------------------

RECIPE_KINDS = ("static", "routed")


def validate_recipe(name: str, recipe: Mapping[str, Any]) -> None:
    """配方格式：权重都是 {qualified_name: 带符号权重}，符号 = 方向、绝对值 = 大小（使用方按 Σ|w| 归一）。

    static: {"kind": "static", "weights": {...}}
    routed: {"kind": "routed", "dimension": 维度, "states": {state: {...}}, "fallback": {...}}
            fallback 可以是空 dict：state 未知 / 该 state 没有配方时不持仓。
    可选 "reference": {"validation_ic_ir": ..., "selection_ic_ir": ..., "score_autocorr": ...}——产出方在
    验证段上报告过的数字，关卡3 拿它做重建一致性检查；没有就不检查。
    """
    kind = recipe.get("kind")
    if kind not in RECIPE_KINDS:
        raise ValueError(f"配方 {name!r} 的 kind={kind!r} 不合法，可选 {RECIPE_KINDS}")
    groups: list[Mapping[str, Any]]
    if kind == "static":
        groups = [recipe["weights"]]
        if not any(float(w) != 0.0 for w in recipe["weights"].values()):
            raise ValueError(f"配方 {name!r} 没有权重非 0 的因子")
    else:
        if not recipe.get("dimension"):
            raise ValueError(f"routed 配方 {name!r} 缺少 dimension")
        groups = [recipe.get("fallback", {}), *recipe["states"].values()]
    for weights in groups:
        for factor, weight in weights.items():
            if not isinstance(factor, str) or not isinstance(weight, (int, float)):
                raise ValueError(f"配方 {name!r} 的权重条目不合法：{factor!r}: {weight!r}")


@dataclass
class RecipeSet:
    track: str
    producer: str
    recipes: dict[str, dict[str, Any]] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    kind = "recipes"

    def factor_names(self) -> list[str]:
        """所有配方用到的因子并集（按首次出现顺序去重）。"""
        seen: dict[str, None] = {}
        for recipe in self.recipes.values():
            groups = [recipe["weights"]] if recipe["kind"] == "static" else [recipe.get("fallback", {}), *recipe["states"].values()]
            for weights in groups:
                for name in weights:
                    seen.setdefault(name, None)
        return list(seen)

    def to_json(self) -> dict[str, Any]:
        for name, recipe in self.recipes.items():
            validate_recipe(name, recipe)
        return {
            "kind": self.kind,
            "schema_version": SCHEMA_VERSION,
            "track": self.track,
            "producer": self.producer,
            "created_at": _now(),
            "meta": self.meta,
            "recipes": self.recipes,
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, Any]) -> "RecipeSet":
        _check_header(raw, "recipes")
        recipes = {name: dict(recipe) for name, recipe in raw.get("recipes", {}).items()}
        for name, recipe in recipes.items():
            validate_recipe(name, recipe)
        return cls(track=raw["track"], producer=raw["producer"], recipes=recipes, meta=dict(raw.get("meta", {})))


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------


def _check_header(raw: Mapping[str, Any], kind: str) -> None:
    if raw.get("kind") != kind:
        raise ValueError(f"交接文件的 kind={raw.get('kind')!r}，期望 {kind!r}")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"交接文件的 schema_version={raw.get('schema_version')!r}，当前代码只认 {SCHEMA_VERSION}")


def write(path: Path, handoff: "CandidateSet | RecipeSet") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(handoff.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _read_raw(path: Path, stage_hint: str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"找不到交接文件 {path}：先跑上游阶段（{stage_hint}）")
    return json.loads(path.read_text(encoding="utf-8"))


def read_candidates(path: Path, *, expect_track: Optional[str] = None) -> CandidateSet:
    candidates = CandidateSet.from_json(_read_raw(path, "产出候选集的阶段"))
    _check_track(path, candidates.track, expect_track)
    return candidates


def read_recipes(path: Path, *, expect_track: Optional[str] = None) -> RecipeSet:
    recipes = RecipeSet.from_json(_read_raw(path, "产出配方集的阶段"))
    _check_track(path, recipes.track, expect_track)
    return recipes


def _check_track(path: Path, actual: str, expected: Optional[str]) -> None:
    if expected is not None and actual != expected:
        raise SystemExit(f"交接文件 {path} 属于研究线 {actual!r}，不是当前的 {expected!r}")


def sign_of(value: Any) -> float:
    """元信息里的带符号统计量（如 ic_ir）-> 方向 ±1；缺失 / 0 / 非数字返回 0（方向未知）。"""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    if v != v:  # NaN
        return 0.0
    return float((v > 0) - (v < 0))
