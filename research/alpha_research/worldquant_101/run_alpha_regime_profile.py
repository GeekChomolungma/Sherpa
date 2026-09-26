"""世坤101研究项目·Regime 全历史体检：对全部已注册的世坤101 alpha（不预先过 `run_screening.py`
的全局 IC_IR 筛选）逐个算 `ic_series`，在 regime 打标（`regime_report()`）的四个维度上做条件 IC 切片，
产出"alpha × 维度 × 状态"的长表体检结果。

故意不依赖 `screening_report.csv` 的 `passed` 列表——regime 体检本身就是一种因子体检，不是
"体检完的因子再体检一遍"。用全局 IC_IR 筛选结果做准入门槛，反而会把 regime 体检最该捞出来
的那类因子先滤掉：`REGIME_ALPHA_EVALUATION_WORKFLOW.md` §6 决策矩阵里"条件进攻型因子"的
示例 Alpha_A，全局 IC_IR 只有 0.11，比 `run_screening.py` 用的 0.15 门槛还低，如果先过一遍
全局筛选就永远轮不到这里——它恰恰是全局表现平庸、但在特定 regime 下很强的那类因子，是这份
体检真正要找的对象。这也是跟 `run_screening.py`/`_category_runner.py` 那条产线彻底解耦、
互不依赖的"并行旁路"（两条线各自独立跑，谁也不需要等谁的结果）。

跟世坤101所有因子一样，部分因子会因为缺行业分类/市值字段 `raise NotImplementedError`（占位
不实现），这里如实跳过并单独计数，不当成 bug 吞掉，也不让它拖累其余因子（跟 `screen_alphas`
处理占位因子的方式一致）。

101 个 alpha 的 `compute()` + `rank_ic()` 互相独立、都只读同一份 `panel`/`forward_returns`，
用 `ProcessPoolExecutor` 按 alpha 分给多个进程算——这一步是 pandas rolling/rank 计算，GIL
下多线程没用，必须是多进程；`panel`/`forward_returns` 通过 `initializer` 只在每个 worker
进程启动时发一次，不随每个 alpha 任务重复发送。没有考虑 GPU：这里的矩阵（几千 bar × 几百
symbol）远够不到 GPU 数据搬运开销划算的规模，真正的计算内核也是 pandas 的 rolling/rank，
硬要搬上 GPU 等于重写 `sherpa.alpha.ops` 整层，而且 GPU dataframe 方案（RAPIDS/cuDF）在
Windows 上不原生支持（需要 WSL2），投入产出比不划算。

算 `ic_series` 之前会先用 `sherpa.metrics.tradability.tradable_mask` 把每期截面里"上线了
但实际没有真实流动性"的 symbol 掩掉（掩成 `NaN`）——加密市场长尾小币持续打印K线但订单簿
早已枯竭是常态，`Universe.as_of()` 只管"有没有上线"，不管"上线后是不是还有真实成交"，直接
拿全部截面 symbol 去算秩相关，插针币会污染 IC 的稳定性,选出来的因子也没法在真实执行时
接得住。这一步只影响这个旁路脚本自己算的 `ic_series`——`rank_ic()`/`quantile_returns()`
本身不用改一行代码，它们已经会正确处理逐期缺失值,把 mask 为 `False` 的位置设成 `NaN`
就等价于"这一期这个 symbol 缺失"。`run_screening.py`/`_category_runner.py` 那条真正决定
仓位的产线目前还没接这个掩码，是有意先在这里验证设计、范围先不铺开。

对应架构分层：
`sherpa.metrics.tradability.tradable_mask`（纯统计，掩码）
`sherpa.risk.neutralize.neutralize`（纯统计，截面中性化残差化，`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`
§3.2）
`sherpa.metrics.factor.conditional_ic_summary`（纯统计，条件切片）
-> `sherpa.backtest.regime_screening.profile_alphas_by_regime`（批量入口）
-> 这里（具体项目跑批 + 落盘）。

`_compute_ic_series` 在算 `rank_ic` 之前，先用可流通性掩码盖掉没有真实流动性的 symbol，再
对剩下的原始分数做中性化残差化（剔除 Beta/Size 暴露）——用残差分数产出的 `ic_series`，才是
`regime_alpha_profile.csv` 真正要回答的问题："剥离掉被动风险暴露之后，这个因子在各个 regime
下还剩多少真实的选币能力"，而不是"这个因子的表现有多少其实是在骑 Beta"。

`USE_NEUTRALIZATION` 开关默认 `True`（标准做法）；手动改成 `False` 会跳过中性化，直接用
原始分数（也就是允许骑 Beta）算 `ic_series`，仅用于跟中性化版本做对照诊断——`OUTPUT_PATH`
会跟着开关自动换文件名（`regime_alpha_profile.csv` / `regime_alpha_profile_without_neutralization.csv`），
两版结果不会互相覆盖。

输出长表里的 `t_stat`/`p_value` 是每个切片 IC 均值的 Newey–West 显著性检验
（`sherpa.metrics.factor.ic_significance`，由 `conditional_ic_summary` 顺带算出），下游
`regime_factor_report.py` 用它做 `04_regime_matrix.csv` 的显著性门槛。

不依赖 `run_regime_report.py` 的产出：regime 打标在本脚本里用同一个 `regime_report()` 现算，
`regime_report.csv` 只是给人看的单独报告。直接运行：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/worldquant_101/run_alpha_regime_profile.py
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.worldquant  # noqa: F401  import 触发 @register_alpha，把 101 个 alpha 都注册进 registry
from sherpa.alpha import registry
from sherpa.backtest.regime_screening import profile_alphas_by_regime, regime_report
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.metrics.factor import rank_ic
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

from data import END_TIME, EXECUTION_DELAY_BARS, HORIZON_BARS, INTERVAL, START_TIME, label_forward_returns, load_universe_panel

BENCHMARK_SYMBOL = "BTCUSDT"

# 中性化开关：默认 True，剥离 Beta/Size 被动暴露算残差 ic_series（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`
# §3.2 的标准做法）。手动改成 False 会直接用原始分数（允许骑 Beta），仅用于跟中性化版本
# 做对照诊断，不建议作为长期默认。
USE_NEUTRALIZATION = True

OUTPUT_PATH = "regime_alpha_profile.csv" if USE_NEUTRALIZATION else "regime_alpha_profile_without_neutralization.csv"

# 多进程 worker 数上限：每个 worker 启动时都会收到一整份 panel/forward_returns/mask/exposures
# 的拷贝。2020 年至今的 4h 全市场数据（~500 symbol × ~13600 bar）每份约 0.8 GB，再加上因子
# 计算时的中间矩阵，默认按 CPU 核数（20 核就是 20 个 worker）开会把内存推到 30~40 GB。
# 默认封顶 12；内存紧张时用环境变量 `SHERPA_MAX_WORKERS` 调小。
MAX_WORKERS = int(os.environ.get("SHERPA_MAX_WORKERS", min(12, os.cpu_count() or 1)))

# worker 进程内的全局状态：`_init_worker` 在每个 worker 进程启动时赋值一次，之后同一个
# worker 处理的每个任务（每个 alpha）都直接复用，不用每个任务都重新反序列化一遍 panel。
_worker_panel = None
_worker_forward_returns = None
_worker_mask = None
_worker_exposures = None


def _init_worker(panel, forward_returns, mask, exposures) -> None:
    global _worker_panel, _worker_forward_returns, _worker_mask, _worker_exposures
    _worker_panel = panel
    _worker_forward_returns = forward_returns
    _worker_mask = mask
    _worker_exposures = exposures


def _compute_ic_series(qualified_name: str) -> tuple[str, "pd.Series | None", "str | None"]:
    """单个 alpha 的 worker 任务：算不出来（占位因子）返回 error 信息，算出来返回 ic_series。

    用 `registry.get(qualified_name)()` 而不是直接 pickle alpha 实例——Windows 的 spawn
    方式起 worker 进程时会重新 import 这个脚本模块（触发 `sherpa.alpha.worldquant` 重新
    注册），每个 worker 自己的 `registry` 里本来就有这份 alpha，没必要跨进程传对象。

    先用 `_worker_mask` 把"当期没有真实流动性"的位置盖成 `NaN`，再对剩下的原始分数做
    `neutralize()` 中性化残差化——先掩码再中性化，是为了不让插针小币的噪声分数混进当期的
    截面回归，跟 `factor_orthogonalization` 现有的"先掩码再算统计量"顺序一致。`rank_ic`
    本身已经会正确处理逐期缺失值，不用改它。
    """
    alpha = registry.get(qualified_name)()
    try:
        history = alpha.compute(_worker_panel)
    except NotImplementedError as exc:
        return qualified_name, None, str(exc)
    history = history.where(_worker_mask)
    if _worker_exposures is not None:
        history = neutralize(history, _worker_exposures)
    forward_returns = _worker_forward_returns.where(_worker_mask)
    return qualified_name, rank_ic(history, forward_returns), None


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    forward_returns = label_forward_returns(panel)
    print(f"IC 标签：持有 {HORIZON_BARS} 根 bar、执行延迟 {EXECUTION_DELAY_BARS} 根 bar（research_config.json 的 label 一节）")

    print("正在计算可流通性掩码（剔除上线了但没有真实流动性的 symbol）……")
    mask = tradable_mask(panel.quote_volume, panel.trades_count)
    print(f"  每期平均 {mask.sum(axis=1).mean():.1f} / {len(panel.symbols)} 个 symbol 通过流通性筛选")

    if USE_NEUTRALIZATION:
        print("正在计算中性化用的风险暴露矩阵（Beta 对 BTCUSDT / Size 用 log(quote_volume)）……")
        exposures = default_style_exposures(panel, benchmark_symbol=BENCHMARK_SYMBOL)
    else:
        print("USE_NEUTRALIZATION=False：跳过中性化，直接用原始分数（允许骑 Beta）算 ic_series，仅供对照……")
        exposures = None

    qualified_names = list(registry.all(family="worldquant").keys())
    score_kind = "残差分数" if USE_NEUTRALIZATION else "原始分数"
    print(f"\n正在用多进程对全部 {len(qualified_names)} 个世坤101 alpha 计算{score_kind}的 ic_series……")

    ic_series_by_alpha: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    processed = 0
    started = time.monotonic()
    print(f"  worker 数：{MAX_WORKERS}（环境变量 SHERPA_MAX_WORKERS 可调）；每个 worker 先接收一份数据拷贝，前几分钟没有输出属正常")
    with ProcessPoolExecutor(
        max_workers=MAX_WORKERS, initializer=_init_worker, initargs=(panel, forward_returns, mask, exposures)
    ) as executor:
        # 用 submit + as_completed 而不是 executor.map：map 按提交顺序返回，排在前面的一个慢因子
        # 会把后面所有已经算完的结果都挡住，进度看起来像卡死；as_completed 谁先算完先报谁。
        futures = [executor.submit(_compute_ic_series, name) for name in qualified_names]
        for future in as_completed(futures):
            qualified_name, ic_series, error = future.result()
            processed += 1
            if error is not None:
                errors[qualified_name] = error
            else:
                ic_series_by_alpha[qualified_name] = ic_series
            elapsed = time.monotonic() - started
            status = "跳过（占位）" if error is not None else "完成"
            print(f"  [{processed}/{len(qualified_names)}] {qualified_name} {status}，已用时 {elapsed / 60:.1f} 分钟", flush=True)

    print(f"算不出来的因子：{len(errors)} 个（缺行业分类/市值，占位不实现）")
    print(f"参与 regime 体检的因子：{len(ic_series_by_alpha)} 个")

    print("\n正在计算 regime 报告矩阵……")
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    print("正在做条件 IC 切片体检……")
    # 长表里每个因子 = 各维度的具体 state 行 + 一行 dimension=unconditional（完整 IC 序列、不看 regime）。
    # 后者是该因子唯一的全历史基线，也是 regime_factor_report 产出 05_global_matrix.csv（关卡2 全局对照组 G0）的来源。
    profile = profile_alphas_by_regime(ic_series_by_alpha, regime)
    profile.to_csv(OUTPUT_PATH, index=False)
    print(f"\n完整 alpha × regime 体检长表已写入 research/alpha_research/worldquant_101/{OUTPUT_PATH}")

    print("\n== 各 alpha 在 regime state 里 ic_ir 偏离全历史基线最大的 20 行 ==")
    # 基线 = 每个 alpha 唯一的 unconditional 行（完整 IC 序列）；按 alpha 合并到它的各 state 行上再相减。
    is_baseline = profile["dimension"] == "unconditional"
    baseline = profile.loc[is_baseline, ["alpha", "ic_ir"]].rename(columns={"ic_ir": "baseline_ic_ir"})
    non_baseline = profile[~is_baseline].dropna(subset=["ic_ir"])
    non_baseline = non_baseline.merge(baseline, on="alpha", how="left")
    non_baseline["ic_ir_gap"] = (non_baseline["ic_ir"] - non_baseline["baseline_ic_ir"]).abs()
    top_gap = non_baseline.sort_values("ic_ir_gap", ascending=False).head(20)
    print(top_gap.to_string(index=False))


if __name__ == "__main__":
    main()
