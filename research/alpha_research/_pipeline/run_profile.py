"""阶段一·Regime 条件 IC 体检（通用版，按研究线 track 配置跑）：对这条研究线的全部因子逐个算
`ic_series`，在 track 指定的 regime 维度上做条件 IC 切片，产出"alpha × 维度 × 状态"长表。

用法（仓库根目录的 run_research.sh / 各研究线的 run_track.sh 会调它）：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/_pipeline/run_profile.py <track_id>

track 决定的东西（`<track>/track.json`，字段见 `research/alpha_research/README.md`）：
- 哪些因子：`alphas.modules` 里定义的已注册因子（可再按 `alphas.family` 过滤）；
- 处理链：`preprocess.tradable_mask`（外层可流通性掩码，开关 + 门槛）、`preprocess.neutralize`
  （剥离 Beta/Size）。关掉中性化的对照版本写到另一个文件名，不覆盖标准版本；
- 看哪些 regime 维度：`regime.dimensions`（比如只看 trend）。
产出写到 `<track>/regime_alpha_profile.csv`（关掉中性化时是 `..._without_neutralization.csv`）。

方法论（最初在世坤101 研究线上建立，所有研究线一致）：
- 不先过全局 IC_IR 筛选：regime 体检要捞的恰恰是"全局平庸、特定 regime 下很强"的条件型因子
  （`REGIME_ALPHA_EVALUATION_WORKFLOW.md` §6），先用全局门槛滤一遍就永远轮不到它们。
- 处理链走 `sherpa.backtest.residual`：原始分数 → 可流通性掩码 → 中性化残差，IC 标签用同一个掩码；
  跟关卡1/2/3 是同一个函数，口径不会分叉。
- 占位因子（`raise NotImplementedError`，比如缺行业/市值数据的世坤因子）如实跳过并计数。
- 输出长表里每个因子另有一行 `dimension=unconditional, state=ALL`（完整 IC 序列，不看 regime），是它的
  全历史基线，也是下游 `05_global_matrix.csv` 的来源；`t_stat`/`p_value` 是 Newey–West 显著性检验。
- 因子之间互相独立，用 `ProcessPoolExecutor` 按因子分给多个进程算（pandas rolling/rank 受 GIL 限制，
  多线程没用）；panel/标签/处理链只在每个 worker 启动时发一次。
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

# 研究线配置 track.py 在 research/_shared/（各关卡也要读），插进 sys.path。
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "_shared"))

from sherpa.alpha import registry
from sherpa.backtest.regime_screening import profile_alphas_by_regime, regime_report
from sherpa.backtest.residual import ScorePreprocessor, residual_score
from sherpa.metrics.factor import rank_ic

from data import (
    BENCHMARK_SYMBOL,
    END_TIME,
    EXECUTION_DELAY_BARS,
    HORIZON_BARS,
    INTERVAL,
    START_TIME,
    label_forward_returns,
    load_universe_panel,
)
from track import Track, load_track

# 多进程 worker 数上限：每个 worker 启动时都会收到一整份 panel/标签/掩码/暴露矩阵的拷贝，全市场 4h
# 数据每份约 0.8 GB，再加上因子计算的中间矩阵，按 CPU 核数全开会把内存推到 30~40 GB。默认封顶 12；
# 内存紧张时用环境变量 `SHERPA_MAX_WORKERS` 调小。
MAX_WORKERS = int(os.environ.get("SHERPA_MAX_WORKERS", min(12, os.cpu_count() or 1)))

# worker 进程内的全局状态：`_init_worker` 在每个 worker 启动时赋值一次，之后同一个 worker 处理的每个
# 因子都直接复用，不用每个任务都重新反序列化一遍 panel。
_worker_panel = None
_worker_forward_returns = None
_worker_preprocessor = None


def _init_worker(track: Track, panel, forward_returns, preprocessor) -> None:
    global _worker_panel, _worker_forward_returns, _worker_preprocessor
    # Windows 的 spawn 方式起 worker 时 registry 是空的：按 track 重新 import 因子模块触发注册，
    # 之后按 qualified_name 现场实例化，不跨进程传 alpha 对象。
    track.import_alpha_modules()
    _worker_panel = panel
    _worker_forward_returns = forward_returns
    _worker_preprocessor = preprocessor


def _compute_ic_series(qualified_name: str) -> tuple[str, "pd.Series | None", "str | None"]:
    """单个因子的 worker 任务：算不出来（占位因子）返回 error 信息，算出来返回 ic_series。"""
    alpha = registry.get(qualified_name)()
    try:
        score = residual_score(alpha, _worker_panel, _worker_preprocessor)
    except NotImplementedError as exc:
        return qualified_name, None, str(exc)
    return qualified_name, rank_ic(score, _worker_forward_returns), None


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("用法：python run_profile.py <track_id 或研究线目录>")
    track = load_track(sys.argv[1])
    qualified_names = track.select_alphas()
    print(f"研究线 {track.id}：{track.description}")
    print(f"  因子 {len(qualified_names)} 个（modules={list(track.alpha_modules)}, family={track.alpha_family}）")
    print(f"  外层可流通性掩码：{track.tradable}；中性化：{track.neutralize}；regime 维度：{list(track.regime_dimensions)}")

    print(f"\n正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    print("正在计算处理链（可流通性掩码 / 中性化用的 Beta、Size 暴露）……")
    preprocessor = ScorePreprocessor.from_panel(
        panel, benchmark_symbol=BENCHMARK_SYMBOL, tradable=track.tradable, neutralize=track.neutralize
    )
    if preprocessor.mask is not None:
        print(f"  每期平均 {preprocessor.mask.sum(axis=1).mean():.1f} / {len(panel.symbols)} 个 symbol 通过流通性筛选")
    forward_returns = preprocessor.mask_labels(label_forward_returns(panel))
    print(f"IC 标签：持有 {HORIZON_BARS} 根 bar、执行延迟 {EXECUTION_DELAY_BARS} 根 bar（research_config.json 的 label 一节）")

    score_kind = "残差分数" if track.neutralize else "原始分数（未剥离 Beta，仅供对照）"
    print(f"\n正在用多进程对 {len(qualified_names)} 个因子计算{score_kind}的 ic_series……")
    workers = max(1, min(MAX_WORKERS, len(qualified_names)))
    print(f"  worker 数：{workers}（环境变量 SHERPA_MAX_WORKERS 可调）；每个 worker 先接收一份数据拷贝，前几分钟没有输出属正常")

    ic_series_by_alpha: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    started = time.monotonic()
    with ProcessPoolExecutor(
        max_workers=workers, initializer=_init_worker, initargs=(track, panel, forward_returns, preprocessor)
    ) as executor:
        # submit + as_completed：谁先算完先报谁，一个慢因子不会把后面已经算完的结果都挡住。
        futures = [executor.submit(_compute_ic_series, name) for name in qualified_names]
        for processed, future in enumerate(as_completed(futures), 1):
            qualified_name, ic_series, error = future.result()
            if error is not None:
                errors[qualified_name] = error
            else:
                ic_series_by_alpha[qualified_name] = ic_series
            status = "跳过（占位）" if error is not None else "完成"
            elapsed = (time.monotonic() - started) / 60
            print(f"  [{processed}/{len(qualified_names)}] {qualified_name} {status}，已用时 {elapsed:.1f} 分钟", flush=True)

    print(f"算不出来的因子：{len(errors)} 个（占位不实现）")
    print(f"参与 regime 体检的因子：{len(ic_series_by_alpha)} 个")
    if not ic_series_by_alpha:
        raise SystemExit("没有任何因子算出 ic_series，不产出长表")

    print("\n正在计算 regime 报告矩阵并做条件 IC 切片……")
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)
    profile = profile_alphas_by_regime(
        ic_series_by_alpha, regime, dimensions=track.regime_dimensions, label_horizon=HORIZON_BARS
    )
    profile.to_csv(track.profile_path, index=False)
    print(f"\n完整 alpha × regime 体检长表已写入 {track.profile_path}")

    print("\n== 各 alpha 在 regime state 里 ic_ir 偏离全历史基线最大的 20 行 ==")
    is_baseline = profile["dimension"] == "unconditional"
    baseline = profile.loc[is_baseline, ["alpha", "ic_ir"]].rename(columns={"ic_ir": "baseline_ic_ir"})
    non_baseline = profile[~is_baseline].dropna(subset=["ic_ir"]).merge(baseline, on="alpha", how="left")
    non_baseline["ic_ir_gap"] = (non_baseline["ic_ir"] - non_baseline["baseline_ic_ir"]).abs()
    print(non_baseline.sort_values("ic_ir_gap", ascending=False).head(20).to_string(index=False))


if __name__ == "__main__":
    main()
