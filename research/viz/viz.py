"""研究结果可视化的命令行入口（用法见同目录 README.md）。

    # 一个 run 的总览
    python research/viz/viz.py run research/alpha_research/MLalpha/runs/lstm_v5

    # 多个 run 同一批指标放一张图（每条线一个模型）
    python research/viz/viz.py compare research/alpha_research/MLalpha/runs/{lgbm_v4,xgb_v5,lstm_v5} --baseline lgbm_v4

输出单个 HTML（双击用浏览器打开），默认写到 `research/viz/output/`。
"""

from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parent))

from figures import compare_page, overview_page  # noqa: E402
from metrics import METRICS, Options, segment_summary  # noqa: E402
from series import (  # noqa: E402
    DEFAULT_COST, DEFAULT_MARKET, DEFAULT_REBALANCE_EVERY, DEFAULT_WEIGHTING, Combo, available_combos, load_market, load_run,
)

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_COMPARE_METRICS = ("rankic_cum", "rankic_diff_cum", "rankic_rolling", "equity", "drawdown")


def _options(args: argparse.Namespace, runs: list) -> Options:
    """组合没指定时：用账本自己声明的默认组合（只做多账本），否则用全局默认（关卡3 的 top10_exit20 / 每 6 根）。"""
    declared = next((run.default_combo for run in runs if run.default_combo is not None), None)
    weighting = args.weighting or (declared.weighting if declared else DEFAULT_WEIGHTING)
    every = args.every or (declared.rebalance_every if declared else DEFAULT_REBALANCE_EVERY)
    return Options(
        combo=Combo(weighting, every, args.case), cost=args.cost,
        ic_window_days=args.ic_window, sharpe_window_days=args.sharpe_window, ic_horizon=args.ic_horizon,
    )


def _write(text: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _market(args: argparse.Namespace):
    """市场背景行：默认 BTCUSDT，`--market none` 不画；没取过数据就提示一下、照常出图。"""
    if args.market.lower() == "none":
        return None
    market = load_market(args.market)
    if market is None:
        print(f"  [提示] 没有 {args.market} 的市场背景数据，图里不画这一行。要画先跑："
              f"CH_HOST=... CH_PASSWORD=... python research/viz/fetch_market.py {args.market}")
    return market


def _target(out: str | None, default_dir: Path, file_name: str) -> Path:
    """`--out` 是 .html 就用它，是目录就放进去，没给就用默认目录。"""
    if out is None:
        return default_dir / file_name
    out_path = Path(out)
    return out_path if out_path.suffix == ".html" else out_path / file_name


def _combo_suffix(opts: Options, default: bool, book: str = "friction") -> str:
    suffix = "" if book == "friction" else f"__{book}"
    if default:
        return suffix
    return suffix + "__" + re.sub(r"[^\w.-]+", "_", f"{opts.combo.weighting}_every{opts.combo.rebalance_every}_{opts.cost}")


def _is_default(args: argparse.Namespace) -> bool:
    return args.weighting is None and args.every is None and args.cost == DEFAULT_COST


def cmd_run(args: argparse.Namespace) -> None:
    market = _market(args)
    for path in args.runs:
        run = load_run(path, args.book)
        opts = _options(args, [run])
        if args.list_combos:
            print(f"{run.name}：{available_combos(run.gross.columns) if run.gross is not None else '无逐 bar 收益'}")
            continue
        target = _target(args.out, OUTPUT_DIR / "runs", f"{run.name}{_combo_suffix(opts, _is_default(args), args.book)}.html")
        written = _write(overview_page(run, opts, market), target)
        print(f"== {run.name}（{opts.combo.label} · {opts.cost}）==")
        print(segment_summary(run, opts).round(4).to_string(index=False))
        for k, v in run.notes.items():
            print(f"  {k}：{v}")
        print(f"  -> {written}")


def _load_compare_run(spec: str, default_book: str):
    """`run目录` 用 --book；`run目录::<book>` 让这一个 run 读别的账本（比如同一个 run 加不加止损放在一起比），
    名字加上 `·<book>` 区分。"""
    path, sep, book = spec.partition("::")
    if not sep:
        return load_run(path, default_book)
    run = load_run(path, book)
    return dataclasses.replace(run, name=f"{run.name}·{book}")


def cmd_compare(args: argparse.Namespace) -> None:
    runs = [_load_compare_run(p, args.book) for p in args.runs]
    opts = _options(args, runs)
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
    target = _target(args.out, OUTPUT_DIR / "compare", f"{name}{_combo_suffix(opts, _is_default(args), args.book)}.html")
    written = _write(compare_page(runs, metrics, opts, baseline, _market(args)), target)
    print(f"比较 {names}，指标 {metrics}，组合 {opts.combo.label} · {opts.cost} -> {written}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="研究结果可视化：一个 run 的总览 / 多个 run 的对比")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("runs", nargs="+",
                        help="run 目录（<研究线>/runs/<run_id>/）；compare 里可以写 <run 目录>::<book> 让这个 run 读别的账本")
    common.add_argument("--weighting", default=None,
                        help=f"权重映射，默认 {DEFAULT_WEIGHTING}（只做多账本默认用它自己声明的组合）")
    common.add_argument("--every", type=int, default=None,
                        help=f"调仓间隔（根 bar），默认 {DEFAULT_REBALANCE_EVERY}（只做多账本默认用它自己声明的组合）")
    common.add_argument("--book", default="friction",
                        help="收益从哪个账本读：friction = 关卡3 多空（默认）；long_only = tradecraft 的只做多回测（含等权基准）；"
                             "friction_stop_<方案> = 关卡3 加止损控制（run_friction.py --stop-control <方案>）")
    common.add_argument("--cost", default=DEFAULT_COST, help=f"成本假设（zero / all_maker / all_taker / stress），默认 {DEFAULT_COST}")
    common.add_argument("--case", default=None, help="run 里有多个 case 时指定一个")
    common.add_argument("--ic-window", type=float, default=20.0, help="滚动 RankIC 窗口（天），默认 20")
    common.add_argument("--ic-horizon", type=int, default=None,
                        help="RankIC 用哪个持有期（根）。默认：总览用 run 自己的主口径；对比时统一成大家都有的口径（ML 6 根 vs tradecraft 1 根时取 6）")
    common.add_argument("--sharpe-window", type=float, default=90.0, help="滚动 Sharpe 窗口（天），默认 90")
    common.add_argument("--market", default=DEFAULT_MARKET,
                        help=f"最上面一行的市场背景（收盘价），默认 {DEFAULT_MARKET}；none = 不画。数据由 fetch_market.py 取")
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
