"""用关卡1 的去冗余结果重写本目录 `config.py` 里的 `REGIME_FACTOR_SETS`（关卡2 的候选因子池）。

上下游关系（research 子项目之间只通过"上游结果 CSV → 下游 config.py"通信，不互相 import 代码）：

    阶段一  run_alpha_regime_profile.py  → regime_alpha_profile.csv
            regime_factor_report.py      → 04_regime_matrix.csv        （显著 + |IC_IR| Top-K）
    关卡1  factor_orthogonalization/refresh_candidates.py → 关卡1 config.REGIME_ALPHA_SETS
            run_orthogonalization.py     → 02_regime_cluster_assignments.csv（keep / drop 建议）
    关卡2  本脚本                        → 关卡2 config.REGIME_FACTOR_SETS   ← 这里

`run_research.sh --refresh-synthesis-candidates`（步骤 8）会在关卡1 跑完后调用本脚本。
只重写 config.py 里 `# >>> REGIME_FACTOR_SETS BEGIN` 与 `# <<< REGIME_FACTOR_SETS END`
之间的内容，文件其它部分一个字不动。

读取规则（以及为什么这样读）
----------------------------
输入是 `02_regime_cluster_assignments.csv`，一行 = 一个因子在一个 (dimension, state) 切片下的
去冗余结论。对每个 (dimension, state)：

1. **只取 `recommendation` 为保留类的行**（`KEEP_RECOMMENDATIONS`）。
   - `keep`：该因子在这个 state 里不冗余，或者是冗余簇里 |IC_IR| 最高、被选为代表的那个；
   - `keep_complementary`：预留给关卡1 以后的"剔除复核"（1a-R，见
     `factor_orthogonalization/INCREMENTAL_TODO.md` §5.0）——被聚类判成冗余、但剥离代表因子
     后残差仍有独立预测力、被改判保留的因子。现在的关卡1 还不会产出这个值，提前兼容。
   - `drop_redundant` 不取：它的信息已经由同簇的代表因子承载，再放进合成只会重复下注。

2. **按该 state 内的 |own_ic_ir| 从高到低排序**。顺序本身不影响合成结果（关卡2 会自己估权重），
   只是让 config.py 里最强的因子排在最前面，方便人读、也方便 diff。

3. **不做任何额外过滤**。显著性门槛（阶段一）和去冗余（关卡1）都已经在上游做完，这里照单全收；
   如果在这里再加一道筛选，就等于在两个地方定义"选因子标准"，以后很难追查某个因子为什么没进来。

4. **小样本 state 照样保留，只加注释**。`own_low_sample=True`（比如 `trend.bull`）的名单可信度
   打折扣，但丢掉整个 state 会让关卡2 在这种行情下无因子可用；关卡2 的做法是把这类 state 的
   权重往全局权重收缩（`README.md` §5.2），而不是在候选池这一层删掉。

5. **某个 state 在 CSV 里完全没有行**（上游这个 state 没有任何可用因子），就写一个空列表并加
   注释说明。关卡2 遇到空列表时应退回全局（不分 regime）的权重。

用法：
    python research/factor_synthesis/refresh_candidates.py [--assignments PATH]
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.py"
DEFAULT_ASSIGNMENTS = HERE.parent / "factor_orthogonalization" / "results" / "02_regime_cluster_assignments.csv"

BEGIN = "# >>> REGIME_FACTOR_SETS BEGIN"
END = "# <<< REGIME_FACTOR_SETS END"

# 视为"保留"的 recommendation 取值，含义见模块 docstring 第 1 条。
KEEP_RECOMMENDATIONS = frozenset({"keep", "keep_complementary"})

# 跟上游 factor_orthogonalization/config.py 相同的维度/state 顺序，diff 时只看到因子名变化。
ORDER: dict[str, list[str]] = {
    "trend": ["bull", "bear", "neutral"],
    "volatility": ["high", "normal", "low"],
    "dispersion": ["high", "normal", "low"],
    "liquidity": ["high", "normal", "starved"],
}


def _as_float(value: str | None) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def _is_true(value: str | None) -> bool:
    return str(value).strip().lower() == "true"


def _short(name: str) -> str:
    """注释里用短名（去掉家族前缀），名单本身仍写完整 qualified_name。"""
    return name.split(".", 1)[-1]


def load_kept(path: Path) -> tuple[dict[tuple[str, str], list[dict]], set[tuple[str, str]]]:
    """读 02_regime_cluster_assignments.csv，返回 ((dimension, state) -> 保留行列表, 出现过的 state 集合)。

    保留行已经按 |own_ic_ir| 从高到低排好（docstring 第 2 条）。
    """
    kept: dict[tuple[str, str], list[dict]] = defaultdict(list)
    seen_states: set[tuple[str, str]] = set()
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            key = (row["dimension"], row["state"])
            seen_states.add(key)
            if row["recommendation"] in KEEP_RECOMMENDATIONS:
                kept[key].append(row)
    for rows in kept.values():
        rows.sort(key=lambda r: -abs(_as_float(r.get("own_ic_ir")) or 0.0))
    return kept, seen_states


def _factor_comment(row: dict) -> str:
    """行尾注释：残差 IC_IR（带方向）+ 如果它代表了一个冗余簇，列出被它吸收的因子。"""
    ic_ir = _as_float(row.get("own_ic_ir"))
    parts = [f"IC_IR={ic_ir:+.3f}" if ic_ir is not None else "IC_IR=N/A"]
    if row["recommendation"] == "keep_complementary":
        parts.append("剔除复核后改判保留")
    members = [m.strip() for m in row.get("cluster_members", "").split("|") if m.strip()]
    absorbed = [_short(m) for m in members if m != row["qualified_name"]]
    if absorbed:
        parts.append(f"代表冗余簇，吸收了 {', '.join(absorbed)}")
    return "  ".join(parts)


def render(kept: dict[tuple[str, str], list[dict]], seen_states: set[tuple[str, str]]) -> str:
    lines = ["REGIME_FACTOR_SETS: dict[str, dict[str, list[str]]] = {"]
    for dimension, states in ORDER.items():
        lines.append(f'    "{dimension}": {{')
        for state in states:
            rows = kept.get((dimension, state), [])
            if (dimension, state) not in seen_states:
                lines.append(f"        # {dimension}.{state}：关卡1 结果里没有这个 state（上游没有可用因子），关卡2 应退回全局权重")
            elif rows and any(_is_true(r.get("own_low_sample")) for r in rows):
                lines.append(f"        # {dimension}.{state} low_sample=True：样本偏少，关卡2 会把它的权重往全局权重收缩")
            lines.append(f'        "{state}": [')
            for row in rows:
                lines.append(f'            "{row["qualified_name"]}",  # {_factor_comment(row)}')
            lines.append("        ],")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--assignments", type=Path, default=DEFAULT_ASSIGNMENTS,
        help="关卡1 的 02_regime_cluster_assignments.csv 路径",
    )
    args = parser.parse_args()

    if not args.assignments.exists():
        raise SystemExit(f"找不到 {args.assignments}，先跑关卡1（run_orthogonalization.py）生成它")

    kept, seen_states = load_kept(args.assignments)

    # 按字节读写并沿用文件原有的换行风格，避免整份 config.py 因为换行符变化在 diff 里全红。
    text = CONFIG_PATH.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{CONFIG_PATH} 里缺少 BEGIN/END 标记，无法定位要重写的区块")

    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    block = render(kept, seen_states).replace("\n", newline)
    CONFIG_PATH.write_bytes(f"{head}{BEGIN}{newline}{block}{newline}{END}{tail}".encode("utf-8"))

    distinct = {row["qualified_name"] for rows in kept.values() for row in rows}
    print(f"已用 {args.assignments} 的保留名单重写 {CONFIG_PATH} 的 REGIME_FACTOR_SETS")
    print(f"  覆盖 {len(kept)} 个 (dimension, state)，去重后共 {len(distinct)} 个因子")


if __name__ == "__main__":
    main()
