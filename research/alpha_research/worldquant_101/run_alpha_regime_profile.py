"""世坤101研究项目·Regime 全历史体检：对全部已注册的世坤101 alpha（不预先过 `run_screening.py`
的全局 IC_IR 筛选）逐个算 `ic_series`，在 `regime_report.csv` 的四个维度上做条件 IC 切片，
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

运行前先跑过 `run_regime_report.py`（产出 `regime_report.csv`），再跑：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/worldquant_101/run_alpha_regime_profile.py
"""

from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor

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

from data import END_TIME, INTERVAL, START_TIME, load_universe_panel

BENCHMARK_SYMBOL = "BTCUSDT"
OUTPUT_PATH = "regime_alpha_profile.csv"

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
    history = neutralize(history, _worker_exposures)
    forward_returns = _worker_forward_returns.where(_worker_mask)
    return qualified_name, rank_ic(history, forward_returns), None


def main() -> None:
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {INTERVAL} bar")

    forward_returns = panel.close.pct_change().shift(-1)

    print("正在计算可流通性掩码（剔除上线了但没有真实流动性的 symbol）……")
    mask = tradable_mask(panel.quote_volume, panel.trades_count)
    print(f"  每期平均 {mask.sum(axis=1).mean():.1f} / {len(panel.symbols)} 个 symbol 通过流通性筛选")

    print("正在计算中性化用的风险暴露矩阵（Beta 对 BTCUSDT / Size 用 log(quote_volume)）……")
    exposures = default_style_exposures(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    qualified_names = list(registry.all(family="worldquant").keys())
    print(f"\n正在用多进程对全部 {len(qualified_names)} 个世坤101 alpha 计算残差分数的 ic_series……")

    ic_series_by_alpha: dict[str, pd.Series] = {}
    errors: dict[str, str] = {}
    processed = 0
    with ProcessPoolExecutor(
        initializer=_init_worker, initargs=(panel, forward_returns, mask, exposures)
    ) as executor:
        for qualified_name, ic_series, error in executor.map(_compute_ic_series, qualified_names):
            processed += 1
            if error is not None:
                errors[qualified_name] = error
            else:
                ic_series_by_alpha[qualified_name] = ic_series
            if processed % 20 == 0 or processed == len(qualified_names):
                print(f"  已完成 {processed}/{len(qualified_names)}")

    print(f"算不出来的因子：{len(errors)} 个（缺行业分类/市值，占位不实现）")
    print(f"参与 regime 体检的因子：{len(ic_series_by_alpha)} 个")

    print("\n正在计算 regime 报告矩阵……")
    regime = regime_report(panel, benchmark_symbol=BENCHMARK_SYMBOL)

    print("正在做条件 IC 切片体检……")
    profile = profile_alphas_by_regime(ic_series_by_alpha, regime)
    profile.to_csv(OUTPUT_PATH, index=False)
    print(f"\n完整 alpha × regime 体检长表已写入 research/alpha_research/worldquant_101/{OUTPUT_PATH}")

    print("\n== 每个 alpha 在各维度上 ic_ir 波动最大的一档（跟 ALL 基线差距最大） ==")
    # 用 merge 而不是把 (alpha, dimension) 设成索引再相减——非 ALL 的那部分一个 (alpha,
    # dimension) 对应好几个 state（bull/bear/neutral...），设成索引后是非唯一 MultiIndex，
    # 没法直接跟按 (alpha, dimension) 唯一索引的 baseline 做逐元素对齐相减。
    baseline = profile.loc[profile["state"] == "ALL", ["alpha", "dimension", "ic_ir"]]
    baseline = baseline.rename(columns={"ic_ir": "baseline_ic_ir"})
    non_baseline = profile[profile["state"] != "ALL"].dropna(subset=["ic_ir"])
    non_baseline = non_baseline.merge(baseline, on=["alpha", "dimension"], how="left")
    non_baseline["ic_ir_gap"] = (non_baseline["ic_ir"] - non_baseline["baseline_ic_ir"]).abs()
    top_gap = non_baseline.sort_values("ic_ir_gap", ascending=False).head(20)
    print(top_gap.to_string(index=False))


if __name__ == "__main__":
    main()
