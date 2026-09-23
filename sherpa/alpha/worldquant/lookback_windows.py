"""爬取世坤101因子（不含 `industry/` 行业组）内部所有回看窗口参数，供频率迁移/定期核查用。

背景：`docs/LOOKBACK_WINDOW_MIGRATION.md` §3 指出，世坤家族里 82 个非占位因子的回看窗口是
论文按美股日频校准、直接写死在每个 `Alpha.compute()` 方法内部的整数常量，散落各处、没有
共享配置——这个脚本不改动任何窗口，只是静态扫描每个因子的 `compute()` 源码，把里面每一处
`ops.ts_*`/`ops.adv`/`ops.delay`/`ops.delta`/`.pct_change`/`_common.rank_price*` 调用的窗口
参数摘出来，配上这个算子的业务含义（详见 `LOOKBACK_WINDOWS_GUIDE.md`），按因子分组打印。

用静态 AST 解析而不是跑真实数据：这是纯源码层面的普查，不需要连 ClickHouse，随时能跑，
每次改完窗口后重新跑一遍就能看到最新状态——不产出需要手动维护的快照文件。

用法：
    python -m sherpa.alpha.worldquant.lookback_windows            # 打印全量报告
    python -m sherpa.alpha.worldquant.lookback_windows --min 20   # 只看最长窗口 >= 20 的因子
    python -m sherpa.alpha.worldquant.lookback_windows --csv out.csv  # 同时写一份 CSV（每行一个窗口）
"""

from __future__ import annotations

import argparse
import ast
import csv
import inspect
import sys
import textwrap
from dataclasses import dataclass, field

# 函数名 -> (位置参数索引, 关键字参数名, 业务含义)。索引/关键字名任意命中一个就取那个参数。
_OPS_WINDOW_SPECS: dict[str, tuple[int, str, str]] = {
    "ts_sum": (1, "window", "窗口内求和（常见于均线分子 sum(x,N)/N，或窗口累计量）"),
    "ts_min": (1, "window", "窗口内最小值（常见于“距自身滚动低点距离”类特征的分母）"),
    "ts_max": (1, "window", "窗口内最大值"),
    "stddev": (1, "window", "窗口内标准差（该字段在窗口内的离散/波动程度）"),
    "ts_product": (1, "window", "窗口内累乘"),
    "ts_rank": (1, "window", "逐 symbol 自比较的时序百分位排名——只跟自己历史比，不跨 symbol 比较，"
                              "天然不受绝对价格量级影响，见 _common.rank_price docstring"),
    "ts_argmax": (1, "window", "窗口内最大值出现的位置索引（0~window-1），本身是无量纲整数"),
    "ts_argmin": (1, "window", "窗口内最小值出现的位置索引（0~window-1），本身是无量纲整数"),
    "ts_corr": (2, "window", "窗口内两个序列的滚动皮尔逊相关系数（对每条腿的线性缩放不敏感）"),
    "ts_cov": (2, "window", "窗口内两个序列的滚动协方差（不像相关系数那样自带缩放）"),
    "decay_linear": (1, "window", "线性衰减加权移动平均，窗口内越新的数据权重越大"),
    "adv": (1, "window", "窗口内平均成交量（Average Volume，论文里叫 adv{d}，d 原本按天）"),
    "delay": (1, "periods", "取 N 根之前的值（纯移位，不是滚动窗口统计量，但同样是“回看多少根”）"),
    "delta": (1, "periods", "跟 N 根之前的差值（原始是绝对差；中性化改造后不少因子已换成 pct_change，"
                            "见 docs/LOOKBACK_WINDOW_MIGRATION.md 关联的那一轮修复）"),
}

# `sherpa.alpha.worldquant._common` 里的函数（不带 `ops.` 前缀，直接按名字导入调用）。
_COMMON_WINDOW_SPECS: dict[str, tuple[int, str, str]] = {
    "rank_price": (1, "periods", "截面排名前先做 pct_change 归一化的安全替代，见 _common.rank_price"),
    "rank_price_distance_from_low": (1, "window", "距自身滚动最低点的百分比距离"),
}
# `rank_price_diff(a, b, reference)` 故意不在上表——它的“窗口”是 reference 这个价格表达式，
# 不是单一整数，脚本会把它单独标注出来而不是硬凑一个数字。

_PCT_CHANGE_MEANING = "跟 N 根之前的百分比涨跌幅（中性化改造引入的安全替代，见 _common.rank_price docstring）"


@dataclass
class WindowUsage:
    operator: str
    value: object  # 解析到具体整数就是 int，解析不出来就是源码文本（比如引用了变量）
    file_lineno: int
    meaning: str


@dataclass
class AlphaWindowReport:
    family: str
    qualified_name: str
    min_lookback: object
    disabled: bool  # compute() 里直接 raise（占位/禁用因子），此时 windows 为空是正常的
    windows: list[WindowUsage] = field(default_factory=list)

    @property
    def max_window(self) -> int:
        ints = [w.value for w in self.windows if isinstance(w.value, (int, float))]
        return int(max(ints)) if ints else 0


def _resolve_arg(call: ast.Call, index: int, kw_name: str) -> ast.AST | None:
    for kw in call.keywords:
        if kw.arg == kw_name:
            return kw.value
    if len(call.args) > index:
        return call.args[index]
    return None


def _literal_or_source(node: ast.AST) -> object:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    try:
        return ast.unparse(node)
    except Exception:
        return "<无法解析>"


def _extract_windows(compute_method) -> list[WindowUsage]:
    source = textwrap.dedent(inspect.getsource(compute_method))
    base_lineno = compute_method.__code__.co_firstlineno
    tree = ast.parse(source)
    usages: list[WindowUsage] = []

    class _Visitor(ast.NodeVisitor):
        def visit_Call(self, node: ast.Call) -> None:
            self.generic_visit(node)
            fn = node.func
            real_line = base_lineno + node.lineno - 1

            if isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name) and fn.value.id == "ops":
                spec = _OPS_WINDOW_SPECS.get(fn.attr)
                if spec is not None:
                    idx, kw, meaning = spec
                    arg = _resolve_arg(node, idx, kw)
                    value = _literal_or_source(arg) if arg is not None else "?"
                    usages.append(WindowUsage(fn.attr, value, real_line, meaning))
                return

            if isinstance(fn, ast.Attribute) and fn.attr == "pct_change":
                arg = _resolve_arg(node, 0, "periods")
                value = _literal_or_source(arg) if arg is not None else 1  # pandas 默认 periods=1
                usages.append(WindowUsage("pct_change", value, real_line, _PCT_CHANGE_MEANING))
                return

            if isinstance(fn, ast.Name):
                if fn.id == "rank_price_diff":
                    usages.append(
                        WindowUsage("rank_price_diff", "(见 reference 参数，非单一窗口)", real_line,
                                    "两个不同价格字段差值的安全替代，用显式 reference 归一化，见 _common.py")
                    )
                    return
                spec = _COMMON_WINDOW_SPECS.get(fn.id)
                if spec is not None:
                    idx, kw, meaning = spec
                    arg = _resolve_arg(node, idx, kw)
                    default = 1 if fn.id == "rank_price" else "?"
                    value = _literal_or_source(arg) if arg is not None else default
                    usages.append(WindowUsage(fn.id, value, real_line, meaning))
                    return

    _Visitor().visit(tree)
    return usages


def _raises_unconditionally(compute_method) -> bool:
    source = textwrap.dedent(inspect.getsource(compute_method))
    tree = ast.parse(source)
    fn_def = tree.body[0]
    return isinstance(fn_def, ast.FunctionDef) and any(isinstance(stmt, ast.Raise) for stmt in fn_def.body)


def crawl() -> list[AlphaWindowReport]:
    """扫描四个非行业家族（`industry/` 按要求忽略）里所有已注册因子的 `compute()`。"""
    import sherpa.alpha.worldquant.composite as composite
    import sherpa.alpha.worldquant.microstructure as microstructure
    import sherpa.alpha.worldquant.momentum_reversal as momentum_reversal
    import sherpa.alpha.worldquant.price_volume as price_volume

    reports: list[AlphaWindowReport] = []
    for mod in (price_volume, momentum_reversal, microstructure, composite):
        family_label = mod.__name__.rsplit(".", 1)[-1]
        for name in mod.__all__:
            cls = getattr(mod, name)
            alpha = cls()
            windows = _extract_windows(cls.compute)
            disabled = not windows and _raises_unconditionally(cls.compute)
            reports.append(
                AlphaWindowReport(
                    family=family_label,
                    qualified_name=alpha.qualified_name,
                    min_lookback=getattr(cls, "min_lookback", None),
                    disabled=disabled,
                    windows=windows,
                )
            )
    return reports


def _print_report(reports: list[AlphaWindowReport], min_window: int) -> None:
    shown = [r for r in reports if r.max_window >= min_window or (min_window <= 0)]
    shown.sort(key=lambda r: (r.family, r.qualified_name))

    current_family = None
    for r in shown:
        if r.family != current_family:
            current_family = r.family
            print(f"\n{'=' * 70}\n{current_family}\n{'=' * 70}")

        print(f"\n{r.qualified_name}  (min_lookback={r.min_lookback})")
        if r.disabled:
            print("  [占位/禁用因子：compute() 直接 raise NotImplementedError，无窗口属正常]")
            continue
        if not r.windows:
            print("  [未发现回看窗口调用——纯逐元素公式，或本脚本白名单未覆盖的算子，人工核对]")
            continue
        for w in r.windows:
            print(f"  L{w.file_lineno:>4}  {w.operator}({w.value})  — {w.meaning}")

    total = len(reports)
    disabled_count = sum(1 for r in reports if r.disabled)
    ge20 = sum(1 for r in reports if r.max_window >= 20)
    lt10 = sum(1 for r in reports if 0 < r.max_window < 10)
    print(f"\n{'-' * 70}")
    print(f"共 {total} 个因子（不含 industry），其中占位/禁用 {disabled_count} 个；"
          f"最长窗口 >=20 根的 {ge20} 个，<10 根的 {lt10} 个。")


def _write_csv(reports: list[AlphaWindowReport], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["family", "alpha", "min_lookback", "disabled", "line", "operator", "value", "meaning"])
        for r in reports:
            if r.disabled or not r.windows:
                writer.writerow([r.family, r.qualified_name, r.min_lookback, r.disabled, "", "", "", ""])
                continue
            for w in r.windows:
                writer.writerow(
                    [r.family, r.qualified_name, r.min_lookback, r.disabled, w.file_lineno, w.operator, w.value, w.meaning]
                )
    print(f"已写入 {path}")


def main() -> None:
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--min", type=int, default=0, help="只显示最长窗口 >= 此值的因子（默认0=全部显示）")
    parser.add_argument("--csv", type=str, default=None, help="额外写一份 CSV（每行一个窗口调用）")
    args = parser.parse_args()

    reports = crawl()
    _print_report(reports, args.min)
    if args.csv:
        _write_csv(reports, args.csv)


if __name__ == "__main__":
    main()
