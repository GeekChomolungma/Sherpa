"""用关卡2 的产出重写本目录 `config.py` 里的 `CASES`（关卡3 要回测的冻结配方）。

上下游关系（research 子项目之间只通过"上游结果 CSV → 下游 config.py"通信，不互相 import 代码）：

    关卡2  factor_synthesis/run_synthesis.py → results/01_scheme_comparison.csv（各方案 IC 对比）
                                              results/03_factor_weights.csv  （各方案实际用的方向 / 权重）
    关卡3  本脚本                             → 关卡3 config.CASES           ← 这里

`run_research.sh --refresh-friction-cases`（步骤 10）会在关卡2 跑完后调用本脚本。只重写 config.py 里
`# >>> CASES BEGIN` 与 `# <<< CASES END` 之间的内容，文件其它部分一个字不动。

读取规则（以及为什么这样读）
----------------------------
1. **合成方案默认全收**（`01_scheme_comparison.csv` 里 `kind=composite` 的全部方案，按验证段 IC_IR 排序）。
   关卡2 只比了 IC，几个方案的 IC_IR 往往只差零点零几，而分数稳定性（换手）差别更大——扣完成本排名
   可能翻转，所以不在进关卡3 之前就砍掉。`--max-composites N` 可以只留验证段 IC_IR 前 N 个。

2. **单因子参照默认收 1 个：选择段 IC_IR 最高的那个**（`--singles N` 可调）。用来回答"合成扣完成本后，
   是否仍然比最强的单因子好"。按**选择段**挑，不按验证段挑：按验证段挑等于先偷看答案再拿它当对照，
   会让对照组虚高。

3. **配方直接取自 `03_factor_weights.csv` 的 `raw_weight`**，不在这里重估：
   - `G0` / `L1` / `L0`：scope 同名的那几行；等权方案的 raw_weight 就是方向（±1），L1 是选择段 IC_IR；
   - `L2-<维度>`：scope 为 `L2-<维度>.<state>` 的行按 state 分组，fallback 用 `L0` 的行——跟关卡2
     `routed_composite(..., fallback=l0)` 的规则一致；
   - 单因子：方向取它在 `G0` 或 `L0` 里的 sign（关卡2 的全局方向，选择段估出）。

4. 关卡2 的结果如果跟关卡2 的 `config.py` 对不上（比如改了候选池却没重跑 `run_synthesis.py`），这里
   不做检查——本脚本只认关卡2 `results/` 里实际跑出来的东西，那才是验证段上被比较过的配方。
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

_HERE = Path(__file__).resolve().parent
CONFIG_PATH = _HERE / "config.py"
SYNTH_RESULTS = _HERE.parent / "factor_synthesis" / "results"
COMPARISON_CSV = SYNTH_RESULTS / "01_scheme_comparison.csv"
WEIGHTS_CSV = SYNTH_RESULTS / "03_factor_weights.csv"

BEGIN = "# >>> CASES BEGIN"
END = "# <<< CASES END"


def _scope_of(scheme: str) -> str:
    """关卡2 的方案名 → `03_factor_weights.csv` 里的 scope 前缀，例如 "L2-volatility 路由等权" → "L2-volatility"。"""
    return scheme.split(" ", 1)[0]


def _weights_by_scope(weights: pd.DataFrame) -> dict[str, dict[str, float]]:
    table: dict[str, dict[str, float]] = defaultdict(dict)
    for row in weights.itertuples(index=False):
        if float(row.raw_weight) != 0.0:
            table[row.scope][row.factor] = float(row.raw_weight)
    return dict(table)


def build_cases(comparison: pd.DataFrame, weights: pd.DataFrame, *, max_composites: int | None, singles: int) -> list[tuple[str, dict, str]]:
    """返回 [(case 名, 配方, 给人看的注释)]，顺序即写进 config.py 的顺序。"""
    scopes = _weights_by_scope(weights)
    validation = comparison[comparison["segment"].str.startswith("validation")].set_index("scheme")
    selection = comparison[comparison["segment"].str.startswith("selection")].set_index("scheme")

    def note(scheme: str) -> str:
        return (
            f"关卡2：验证段 IC_IR={validation.at[scheme, 'ic_ir']:+.3f}，选择段 IC_IR={selection.at[scheme, 'ic_ir']:+.3f}，"
            f"验证段 score_autocorr={validation.at[scheme, 'score_autocorr']:.3f}"
        )

    cases: list[tuple[str, dict, str]] = []
    composites = validation[validation["kind"] == "composite"].sort_values("ic_ir", ascending=False)
    if max_composites is not None:
        composites = composites.head(max_composites)
    for scheme in composites.index:
        scope = _scope_of(scheme)
        if scope.startswith("L2-"):
            states = {
                key.split(".", 1)[1]: factors
                for key, factors in scopes.items()
                if key.startswith(f"{scope}.")
            }
            if not states:
                raise SystemExit(f"{WEIGHTS_CSV.name} 里没有 {scope}.<state> 的行，无法重建 {scheme!r}")
            if "L0" not in scopes:
                raise SystemExit(f"{WEIGHTS_CSV.name} 里没有 L0 的行：{scheme!r} 的 fallback 无从重建")
            recipe = {"kind": "routed", "dimension": scope[len("L2-"):], "states": states, "fallback": scopes["L0"]}
        else:
            if scope not in scopes:
                raise SystemExit(f"{WEIGHTS_CSV.name} 里没有 scope={scope} 的行，无法重建 {scheme!r}")
            recipe = {"kind": "static", "weights": scopes[scope]}
        cases.append((scheme, recipe, note(scheme)))

    single_rows = selection[selection["kind"] == "single"].sort_values("ic_ir", ascending=False).head(singles)
    global_signs = {**scopes.get("L0", {}), **scopes.get("G0", {})}
    for scheme in single_rows.index:
        name = scheme.split(":", 1)[1]
        if name not in global_signs:
            raise SystemExit(f"单因子 {name} 在 {WEIGHTS_CSV.name} 的 G0 / L0 里都没有方向，无法重建")
        sign = 1.0 if global_signs[name] > 0 else -1.0
        cases.append((scheme, {"kind": "static", "weights": {name: sign}}, note(scheme) + "（单因子参照，按选择段 IC_IR 挑选）"))
    return cases


def _format_weights(weights: dict[str, float], indent: str) -> list[str]:
    lines = [f"{indent}{{"]
    lines += [f"{indent}    {name!r}: {weight!r}," for name, weight in weights.items()]
    lines.append(f"{indent}}}")
    return lines


def render_block(cases: list[tuple[str, dict, str]]) -> str:
    lines = [BEGIN, "CASES: dict[str, dict[str, Any]] = {"]
    for name, recipe, comment in cases:
        lines.append(f"    # {comment}")
        lines.append(f"    {name!r}: {{")
        lines.append(f"        'kind': {recipe['kind']!r},")
        if recipe["kind"] == "static":
            weight_lines = _format_weights(recipe["weights"], "        ")
            lines.append("        'weights': " + weight_lines[0].strip())
            lines += weight_lines[1:-1] + [weight_lines[-1] + ","]
        else:
            lines.append(f"        'dimension': {recipe['dimension']!r},")
            lines.append("        'states': {")
            for state, weights in recipe["states"].items():
                weight_lines = _format_weights(weights, "            ")
                lines.append(f"            {state!r}: " + weight_lines[0].strip())
                lines += weight_lines[1:-1] + [weight_lines[-1] + ","]
            lines.append("        },")
            weight_lines = _format_weights(recipe["fallback"], "        ")
            lines.append("        'fallback': " + weight_lines[0].strip())
            lines += weight_lines[1:-1] + [weight_lines[-1] + ","]
        lines.append("    },")
    lines.append("}")
    lines.append(END)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="用关卡2 的 results 重写关卡3 config.py 的 CASES")
    parser.add_argument("--max-composites", type=int, default=None, help="只收验证段 IC_IR 前 N 个合成方案（默认全收）")
    parser.add_argument("--singles", type=int, default=1, help="单因子参照个数，按选择段 IC_IR 挑（默认 1，0 = 不要）")
    args = parser.parse_args()

    for path in (COMPARISON_CSV, WEIGHTS_CSV):
        if not path.exists():
            raise SystemExit(f"找不到 {path}：先跑关卡2 run_synthesis.py")
    comparison = pd.read_csv(COMPARISON_CSV)
    weights = pd.read_csv(WEIGHTS_CSV)
    cases = build_cases(comparison, weights, max_composites=args.max_composites, singles=args.singles)

    text = CONFIG_PATH.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"{CONFIG_PATH} 里找不到 {BEGIN} / {END} 标记")
    CONFIG_PATH.write_text(pattern.sub(lambda _: render_block(cases), text, count=1), encoding="utf-8")

    print(f"已重写 {CONFIG_PATH} 的 CASES，共 {len(cases)} 个 case：")
    for name, recipe, _ in cases:
        detail = f"按 {recipe['dimension']} 路由，{len(recipe['states'])} 个 state" if recipe["kind"] == "routed" else f"{len(recipe['weights'])} 个因子"
        print(f"  {name}（{detail}）")


if __name__ == "__main__":
    main()
