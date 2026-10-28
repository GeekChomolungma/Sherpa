"""研究结果可视化的命令行入口（用法见同目录 README.md）。

    # 一个 run 的总览
    python research/viz/viz.py run research/alpha_research/MLalpha/runs/lstm_v5

    # 多个 run 同一批指标放一张图（每条线一个模型）
    python research/viz/viz.py compare research/alpha_research/MLalpha/runs/{lgbm_v4,xgb_v5,lstm_v5} --baseline lgbm_v4

输出单个 HTML（双击用浏览器打开），默认写到 `research/viz/output/`。
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from figures import compare_page, overview_page  # noqa: E402
from metrics import METRICS, Options, segment_summary  # noqa: E402
from series import DEFAULT_COST, DEFAULT_REBALANCE_EVERY, DEFAULT_WEIGHTING, Combo, available_combos, load_run  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_COMPARE_METRICS = ("rankic_cum", "rankic_diff_cum", "rankic_rolling", "equity", "drawdown")


def _options(args: argparse.Namespace) -> Options:
    return Options(
        combo=Combo(args.weighting, args.every, args.case), cost=args.cost,
        ic_window_days=args.ic_window, sharpe_window_days=args.sharpe_window,
    )


def _write(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _target(out: str | None, default_dir: Path, file_name: str) -> Path:
    """`--out` 是 .html 就用它，是目录就放进去，没给就用默认目录。"""
    if out is None:
        return default_dir / file_name
    out_path = Path(out)
    return out_path if out_path.suffix == ".html" else out_path / file_name


def _combo_suffix(opts: Options, default: bool) -> str:
    if default:
        return ""
    return "__" + re.sub(r"[^\w.-]+", "_", f"{opts.combo.weighting}_every{opts.combo.rebalance_every}_{opts.cost}")


def _is_default(args: argparse.Namespace) -> bool:
    return (args.weighting, args.every, args.cost) == (DEFAULT_WEIGHTING, DEFAULT_REBALANCE_EVERY, DEFAULT_COST)


def cmd_run(args: argparse.Namespace) -> None:
    opts = _options(args)
    for path in args.runs:
        run = load_run(path)
        if args.list_combos:
            print(f"{run.name}：{available_combos(run.gross.columns) if run.gross is not None else '无逐 bar 收益'}")
            continue
        target = _target(args.out, OUTPUT_DIR / "runs", f"{run.name}{_combo_suffix(opts, _is_default(args))}.html")
        written = _write(overview_page(run, opts), target)
        print(f"== {run.name}（{opts.combo.label} · {opts.cost}）==")
        print(segment_summary(run, opts).round(4).to_string(index=False))
        for k, v in run.notes.items():
            print(f"  {k}：{v}")
        print(f"  -> {written}")


def cmd_compare(args: argparse.Namespace) -> None:
    opts = _options(args)
    runs = [load_run(p) for p in args.runs]
    names = [r.name for r in runs]
    baseline = None
    if args.baseline:
        if args.baseline not in names:
            raise SystemExit(f"--baseline {args.baseline} 不在这次比较的 run 里：{names}")
        baseline = runs[names.index(args.baseline)]
    metrics = list(args.metrics or DEFAULT_COMPARE_METRICS)
    if baseline is None and "rankic_diff_cum" in metrics:
        metrics.remove("rankic_diff_cum")
    unknown = [m for m in metrics if m not in METRICS]
    if unknown:
        raise SystemExit(f"未知指标 {unknown}；可选的有 {list(METRICS)}")
    name = args.name or "+".join(names)
    target = _target(args.out, OUTPUT_DIR / "compare", f"{name}{_combo_suffix(opts, _is_default(args))}.html")
    written = _write(compare_page(runs, metrics, opts, baseline), target)
    print(f"比较 {names}，指标 {metrics}，组合 {opts.combo.label} · {opts.cost} -> {written}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="研究结果可视化：一个 run 的总览 / 多个 run 的对比")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("runs", nargs="+", help="run 目录（<研究线>/runs/<run_id>/）")
    common.add_argument("--weighting", default=DEFAULT_WEIGHTING, help=f"权重映射，默认 {DEFAULT_WEIGHTING}")
    common.add_argument("--every", type=int, default=DEFAULT_REBALANCE_EVERY, help=f"调仓间隔（根 bar），默认 {DEFAULT_REBALANCE_EVERY}")
    common.add_argument("--cost", default=DEFAULT_COST, help=f"成本假设（zero / all_maker / all_taker / stress），默认 {DEFAULT_COST}")
    common.add_argument("--case", default=None, help="run 里有多个 case 时指定一个")
    common.add_argument("--ic-window", type=float, default=20.0, help="滚动 RankIC 窗口（天），默认 20")
    common.add_argument("--sharpe-window", type=float, default=90.0, help="滚动 Sharpe 窗口（天），默认 90")
    common.add_argument("--out", default=None, help="输出目录或 .html 文件，默认 research/viz/output/")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", parents=[common], help="一个（或几个，各出一页）run 的总览")
    run.add_argument("--list-combos", action="store_true", help="只列出 run 里有哪些组合")
    run.set_defaults(func=cmd_run)
    compare = sub.add_parser("compare", parents=[common], help="多个 run 的同一批指标放一张图")
    compare.add_argument("--metrics", nargs="+", default=None,
                         help=f"指标（默认 {' '.join(DEFAULT_COMPARE_METRICS)}）；可选 {' '.join(METRICS)}")
    compare.add_argument("--baseline", default=None, help="基线 run 名（目录名），rankic_diff_cum 要用")
    compare.add_argument("--name", default=None, help="输出文件名（默认各 run 名用 + 连起来）")
    compare.set_defaults(func=cmd_compare)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
