"""关卡2 的透传模式：研究线不需要合成方案对比时，把候选集直接变成配方集交给关卡3。

不取数、不估计任何东西——方向全部取自候选集条目里带符号的统计量（阶段一在**选择段**上算出的 IC_IR，
关卡1 真跑过的话是它在同一段上重算的值），权重一律等权。所以这些配方**没有经过关卡2 在验证段上的比较**，
关卡3 的一致性检查对它们也不适用（配方里不带 `reference`）。配方名统一加 `直通·` 前缀，跟关卡2 真跑产出的
方案区分开，读关卡3 结果时一眼能看出来。

产出哪些配方由研究线 `track.json` 的 `stages.synthesis.passthrough` 决定（默认全开）：

- `singles`：每个候选因子单独一个配方（`single:<因子>`）。true = 全部；整数 N = 按全历史 |IC_IR| 取前 N 个；
- `equal_weight`：`直通·G0 全局等权`（全局名单）和 `直通·L0 并集等权`（各 state 名单的并集）；
- `routed`：候选集里的每个 regime 维度一个 `直通·L2-<维度> 路由等权`：当前 bar 处在哪个 state 就用那个 state 的
  名单（方向取该 state 的 IC_IR 符号），state 未知 / 名单为空时退回 L0——跟关卡2 真跑时 L2 的路由规则一致。

方向：全局方向优先用条目里的 `baseline_ic_ir`（完整 IC 序列），没有就用全局名单里的 `ic_ir`，再没有就用它在
第一个出现的 state 里的 `ic_ir`；state 内方向用该 state 的 `ic_ir`，为 0 / 缺失时退回全局方向。

**等效配方去重**：候选因子很少时，上面几类配方经常退化成同一个东西（比如只有一个因子显著时，G0、L2 路由、单因子
参照都是"只用这一个因子"），关卡3 会把同一个配方回测好几遍。所以按"每根 bar 实际用的权重"判等效：
routed 配方如果每个 state 的权重都跟 fallback 一样，就等于一个 static 配方；权重按 Σ|w| 归一后比较。等效的配方只留
第一个（顺序：G0 → L0 → L2 → 单因子），被合并掉的名字记在留下那个配方的 `equivalent_to` 里，关卡3 结果里查得到。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
import handoff  # noqa: E402

PREFIX = "直通·"


def _global_signs(candidates: handoff.CandidateSet) -> dict[str, float]:
    global_ic = {f["name"]: f.get("ic_ir") for f in candidates.global_set.factors}
    signs: dict[str, float] = {}
    for name, entry in candidates.factor_entries().items():
        for value in (entry.get("baseline_ic_ir"), global_ic.get(name), entry.get("ic_ir")):
            sign = handoff.sign_of(value)
            if sign != 0.0:
                signs[name] = sign
                break
    return signs


def _baseline_strength(candidates: handoff.CandidateSet) -> dict[str, float]:
    strength = {}
    for name, entry in candidates.factor_entries().items():
        for value in (entry.get("baseline_ic_ir"), entry.get("ic_ir")):
            try:
                v = abs(float(value))
            except (TypeError, ValueError):
                continue
            if v == v:
                strength[name] = v
                break
    return strength


def _equal_weights(names: list[str], signs: Mapping[str, float]) -> dict[str, float]:
    return {name: signs[name] for name in names if signs.get(name, 0.0) != 0.0}


def _normalized(weights: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    """按 Σ|w| 归一后的权重（关卡3 合成时也是这么归一的），排好序，可以当比较 / 字典的 key。"""
    total = sum(abs(w) for w in weights.values() if w != 0.0)
    return tuple(sorted((name, round(w / total, 12)) for name, w in weights.items() if w != 0.0)) if total else ()


def _effective_key(recipe: Mapping[str, Any]) -> tuple:
    """配方"每根 bar 实际用什么权重"的规范形式：两个配方 key 相同就是等效的。

    routed 配方里跟 fallback 相同的 state 等于没写（反正退回 fallback）；所有 state 都跟 fallback 相同时，
    它就是一个 static 配方。
    """
    if recipe["kind"] == "static":
        return ("static", _normalized(recipe["weights"]))
    fallback = _normalized(recipe.get("fallback", {}))
    states = tuple(sorted(
        (state, key) for state, weights in recipe["states"].items() if (key := _normalized(weights)) != fallback
    ))
    if not states:
        return ("static", fallback)
    return ("routed", recipe["dimension"], states, fallback)


def dedupe_recipes(recipes: Mapping[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """等效配方只留第一个，被合并掉的名字记进留下那个配方的 `equivalent_to`。"""
    kept: dict[str, dict[str, Any]] = {}
    owner: dict[tuple, str] = {}
    for name, recipe in recipes.items():
        key = _effective_key(recipe)
        if key in owner:
            kept[owner[key]].setdefault("equivalent_to", []).append(name)
            continue
        owner[key] = name
        kept[name] = dict(recipe)
    return kept


def direct_recipes(candidates: handoff.CandidateSet, options: Mapping[str, Any], *, track_id: str) -> handoff.RecipeSet:
    signs = _global_signs(candidates)
    union = candidates.regime_union()
    recipes: dict[str, dict[str, Any]] = {}

    l0 = _equal_weights(union, signs)
    if options.get("equal_weight", True):
        g0 = _equal_weights(candidates.global_set.names, signs)
        if g0:
            recipes[f"{PREFIX}G0 全局等权"] = {"kind": "static", "weights": g0}
        if l0:
            recipes[f"{PREFIX}L0 并集等权"] = {"kind": "static", "weights": l0}

    if options.get("routed", True):
        for dim, states in candidates.regime_sets.items():
            routed_states = {}
            for state, cands in states.items():
                weights = {}
                for f in cands.factors:
                    sign = handoff.sign_of(f.get("ic_ir")) or signs.get(f["name"], 0.0)
                    if sign != 0.0:
                        weights[f["name"]] = sign
                if weights:
                    routed_states[state] = weights
            if routed_states:
                recipes[f"{PREFIX}L2-{dim} 路由等权"] = {
                    "kind": "routed", "dimension": dim, "states": routed_states, "fallback": dict(l0),
                }

    singles = options.get("singles", True)
    if singles:
        names = [n for n in dict.fromkeys(candidates.global_set.names + union) if signs.get(n, 0.0) != 0.0]
        if singles is not True:
            strength = _baseline_strength(candidates)
            names = sorted(names, key=lambda n: -strength.get(n, 0.0))[: int(singles)]
        for name in names:
            recipes[f"single:{name}"] = {"kind": "static", "weights": {name: signs[name]}}

    return handoff.RecipeSet(
        track=track_id,
        producer="synthesis:passthrough",
        recipes=dedupe_recipes(recipes),
        meta={
            "input_producer": candidates.producer,
            "options": dict(options),
            "note": "透传：方向取自候选集（选择段 IC 符号），等权；未经关卡2 在验证段上比较",
        },
    )
