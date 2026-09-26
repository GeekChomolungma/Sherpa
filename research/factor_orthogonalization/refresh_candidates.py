"""用最新的 `04_regime_matrix.csv` 重写 `config.py` 里 `REGIME_ALPHA_SETS` 的候选池（Top-K）。

`factor_orthogonalization` 的候选池设计上是手动维护、不自动继承体检结果（见 README）——
这个脚本是显式的、需要主动调用的例外：`run_research.sh --refresh-candidates` 会在跑正交化
之前调它，避免"上游因子公式/窗口变了、重跑了体检，候选池还是上一版的旧名单"这种对不上的情况。
只重写 config.py 里 `# >>> REGIME_ALPHA_SETS BEGIN` 和 `# <<< REGIME_ALPHA_SETS END` 两个
标记之间的内容，文件其它部分一个字不动。

04 矩阵本身已经做过显著性筛选（`regime_factor_report.py --min-abs-t`，默认 |t| >= 3），
这里照单全收、不再二次过滤；某个 state 显著因子不足 Top-K 时，名单就只有那几个，并在
config.py 里写一行注释说明原因。

用法：
    python research/factor_orthogonalization/refresh_candidates.py [--top-k 5] [--matrix PATH]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.py"
DEFAULT_MATRIX = HERE.parent / "regime_factor_report" / "results" / "04_regime_matrix.csv"

BEGIN = "# >>> REGIME_ALPHA_SETS BEGIN"
END = "# <<< REGIME_ALPHA_SETS END"

# 跟 config.py 原有的维度/state 顺序保持一致，diff 时只看到因子名变化，不看到顺序抖动。
ORDER: dict[str, list[str]] = {
    "trend": ["bull", "bear", "neutral"],
    "volatility": ["high", "normal", "low"],
    "dispersion": ["high", "normal", "low"],
    "liquidity": ["high", "normal", "starved"],
}


def _load_matrix(path: Path) -> dict[tuple[str, str], dict]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return {(row["dimension"], row["state"]): row for row in csv.DictReader(f)}


def _render(matrix: dict[tuple[str, str], dict], top_k: int) -> str:
    lines = ["REGIME_ALPHA_SETS: dict[str, dict[str, list[str]]] = {"]
    for dimension, states in ORDER.items():
        lines.append(f'    "{dimension}": {{')
        for state in states:
            row = matrix.get((dimension, state))
            if row is None:
                raise SystemExit(f"{path_hint()} 里没有 ({dimension}, {state}) 这一行，无法生成候选池")
            names = [row[f"top{i}_alpha"] for i in range(1, top_k + 1) if row.get(f"top{i}_alpha")]
            if str(row.get("low_sample", "")).strip().lower() == "true":
                lines.append(f"        # {dimension}.{state} low_sample=True：样本偏少，排行榜可信度打折扣")
            # 04 矩阵只收通过显著性门槛（|t| >= min_abs_t）的因子，不够 top_k 个时不拿不显著的凑数。
            # 少于 2 个时 run_orthogonalization.py 会跳过这个 state（没有"对"可以算相关）。
            if len(names) < top_k and row.get("significant_count", "") != "":
                lines.append(
                    f"        # {dimension}.{state}：只有 {row['significant_count']}/{row.get('candidate_count', '?')} "
                    f"个因子通过显著性门槛 |t| >= {_fmt_number(row.get('min_abs_t', '?'))}"
                )
            lines.append(f'        "{state}": [')
            lines.extend(f'            "{name}",' for name in names)
            lines.append("        ],")
        lines.append("    },")
    lines.append("}")
    return "\n".join(lines)


def _fmt_number(value: str) -> str:
    """CSV 里的浮点数是 `3.00000000` 这种定长格式，写进注释时收成 `3`。"""
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def path_hint() -> str:
    return "04_regime_matrix.csv"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-k", type=int, default=5, help="每个 state 取前几名（04 矩阵最多有 top1~top5）")
    parser.add_argument("--matrix", type=Path, default=DEFAULT_MATRIX, help="04_regime_matrix.csv 路径")
    args = parser.parse_args()

    if not args.matrix.exists():
        raise SystemExit(f"找不到 {args.matrix}，先跑 regime_factor_report 生成它")

    # 按字节读写并沿用文件原有的换行风格，避免整份 config.py 因为换行符变化在 diff 里全红。
    text = CONFIG_PATH.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    if BEGIN not in text or END not in text:
        raise SystemExit(f"{CONFIG_PATH} 里缺少 BEGIN/END 标记，无法定位要重写的区块")

    head, rest = text.split(BEGIN, 1)
    _, tail = rest.split(END, 1)
    block = _render(_load_matrix(args.matrix), args.top_k).replace("\n", newline)
    CONFIG_PATH.write_bytes(f"{head}{BEGIN}{newline}{block}{newline}{END}{tail}".encode("utf-8"))

    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"已用 {args.matrix} 的 Top{args.top_k} 重写 {CONFIG_PATH} 的 REGIME_ALPHA_SETS")


if __name__ == "__main__":
    main()
