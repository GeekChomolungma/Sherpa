"""三大工程关卡 · 关卡1：因子相关性分析与正交化（按 regime state 切片）。

对 `config.REGIME_ALPHA_SETS` 里手动圈定的"12 个 regime 状态各自的候选因子集"，在**每个
state 自己的历史切片内**逐对计算截面 Spearman 相关，按 `config.CORRELATION_THRESHOLD` 做
单链聚类，每簇只保留该 state 切片内信噪比（|IC_IR|）最高的一个代表因子——
`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §4 关卡1 的落地实现。

**为什么要按 regime state 切片，而不是算一次全历史相关性了事**：关卡2（基于微观 Regime 的
动态多因子合成）最终是"regime 命中 state X 时，从 X 专属的因子集合里挑权重"，所以两个因子
是否冗余，必须在它们真正会被放进同一个 state 的那段历史上检验——全历史看起来不太相关的一
对因子，完全可能在具体某个 state（比如 trend=bull 这种样本本来就少的极端切片）里其实高度
重合，全局分析会漏掉这种情况。

跟阶段一体检（`research/regime_factor_report/`、`research/alpha_research/worldquant_101/`）刻意不共享
任何中间结果：候选池只认 `config.py` 手写的名单，不读它们的 CSV。但 regime 打标本身复用
`sherpa.backtest.regime_screening.regime_report()`——这是核心 sherpa 模块，不是某个
research 子项目的 CSV 产出，复用它不违反"跟 research 子项目解耦"的边界，反而能保证这里说
的 state 跟 `04_regime_matrix.csv` 里说的是同一件事。

两个层面的统计量都复用 `sherpa.metrics.factor`：
1. **因子 vs 未来收益**（`rank_ic` + `conditional_ic_summary`）：衡量单个因子在某个 state
   切片内自己的信噪比，簇内选代表因子时要用。
2. **因子 vs 因子**（同样是 `rank_ic` + `conditional_ic_summary`，非标准用法）：`rank_ic()`
   本质只是"逐期对两个 (T,N) 矩阵做截面 Spearman corrwith"，喂两个因子的历史分数就能拿到
   逐期截面相关序列；再把这条序列当成一条"ic_series"喂给 `conditional_ic_summary()`，就能
   按 regime state 分组拿到每个切片自己的相关均值——不需要另外写条件相关性计算逻辑。

两类序列都只对全历史算一次，之后对每个 (dimension, state) 只是按 regime 分组取一行，不会
因为拆成 12 个 state 就把计算量乘以 12。

**候选因子先中性化残差化，再进相关性聚类**（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2/
关卡1 的顺序结论）：`_resolve_histories()` 里每个因子的原始分数先套可流通性掩码，再用
`sherpa.risk.neutralize.neutralize()` 剔除对 Beta/Size 的被动暴露。原因是这里做聚类判断
的"高相关"本该衡量"两个因子是否提供重复信息"——如果不先中性化，两个因子只要共同承担了
同一份 Beta 暴露，相关系数照样会很高，会被错误地当成"信息冗余"聚成一簇，实际上它们只是
共享了同一份风险底色，不是在表达同一份选股信息。

运行前先设好 ClickHouse 连接环境变量（同 `research/alpha_research/worldquant_101/`）：
    CH_HOST=... CH_PASSWORD=... python research/factor_orthogonalization/run_orthogonalization.py
"""

from __future__ import annotations

import importlib
import sys
from itertools import combinations
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd

import sherpa.alpha.custom  # noqa: F401  触发内置三大家族的 @register_alpha 注册
import sherpa.alpha.tradingview  # noqa: F401
import sherpa.alpha.worldquant  # noqa: F401
from sherpa.alpha import registry
from sherpa.backtest.regime_screening import regime_report
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.metrics.factor import conditional_ic_summary, ic_summary, rank_ic
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

from clustering import cluster_by_correlation
from config import (
    CORRELATION_THRESHOLD,
    EXTRA_IMPORTS,
    LOW_SAMPLE_MIN_FRACTION,
    LOW_SAMPLE_MIN_SAMPLES,
    REGIME_ALPHA_SETS,
    REGIME_BENCHMARK_SYMBOL,
    UNCONDITIONAL_ALPHAS,
)
from data import EXECUTION_DELAY_BARS, HORIZON_BARS, label_forward_returns, load_universe_panel

# 相对脚本自身所在目录解析，不依赖进程当前工作目录（cwd）——`python
# research/factor_orthogonalization/run_orthogonalization.py` 从仓库根目录运行时，
# cwd 是仓库根目录而不是这个脚本所在目录，如果 PAIRS_PATH/CLUSTERS_PATH 写成相对 cwd
# 的 "results/..."，会去找一个仓库根目录下根本不存在的 results/ 文件夹，直接报错崩溃。
_RESULTS_DIR = Path(__file__).resolve().parent / "results"
PAIRS_PATH = _RESULTS_DIR / "01_regime_factor_correlation_pairs.csv"
CLUSTERS_PATH = _RESULTS_DIR / "02_regime_cluster_assignments.csv"

# 不区分 regime 的全历史对照组用这对哨兵值占位 dimension/state，跟真实的 4 个 regime
# 维度、12 个 state 明显区分开，不会在输出里混淆。
UNCONDITIONAL_DIMENSION = "unconditional"
UNCONDITIONAL_STATE = "ALL"


def _groups() -> list[tuple[str, str, list[str]]]:
    """把 `config.REGIME_ALPHA_SETS` 摊平成 `(dimension, state, alphas)` 列表，顺序固定
    （先 REGIME_ALPHA_SETS 声明顺序，`unconditional` 永远排最后），方便结果可复现地排序。
    """
    groups: list[tuple[str, str, list[str]]] = []
    for dimension, states in REGIME_ALPHA_SETS.items():
        for state, alphas in states.items():
            groups.append((dimension, state, list(alphas)))
    if UNCONDITIONAL_ALPHAS:
        groups.append((UNCONDITIONAL_DIMENSION, UNCONDITIONAL_STATE, list(UNCONDITIONAL_ALPHAS)))
    return groups


def _all_referenced_alphas(groups: list[tuple[str, str, list[str]]]) -> list[str]:
    seen: dict[str, None] = {}
    for _, _, alphas in groups:
        for name in alphas:
            seen.setdefault(name, None)
    return list(seen)


def _resolve_histories(
    names: list[str], panel, mask: pd.DataFrame, exposures: dict[str, pd.DataFrame]
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """按 qualified_name 逐个算历史分数，套流通性掩码，再中性化残差化。

    在 registry 里找不到（名字写错/对应家族没注册）直接 `KeyError` 崩溃，不静默跳过——
    候选池是手写的，名字打错属于配置错误，应该第一时间暴露。因子本身算不出来（占位实现
    `raise NotImplementedError`，比如缺行业分类/市值的世坤101因子）才计入 `errors` 并跳过。

    先掩码、再中性化：不让插针小币的噪声分数混进当期的截面回归，跟
    `alpha_research/worldquant_101/run_alpha_regime_profile.py` 的处理顺序一致。返回的是
    剥离过 Beta/Size 暴露的残差分数——后续的相关性聚类、`own_ic_ir` 全部基于这份残差算。
    """
    histories: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for qualified_name in names:
        alpha = registry.get(qualified_name)()
        try:
            history = alpha.compute(panel)
        except NotImplementedError as exc:
            errors[qualified_name] = str(exc)
            continue
        history = history.where(mask)
        histories[qualified_name] = neutralize(history, exposures)
    return histories, errors


def _pair_key(a: str, b: str) -> tuple[str, str]:
    """相关性序列缓存统一用排序后的元组当 key——同一对因子在不同 state 分组里出现的
    先后顺序可能不一样，缓存必须跟顺序无关，否则会重复计算或查缓存 miss。"""
    return (a, b) if a <= b else (b, a)


def _needed_pair_series(
    groups: list[tuple[str, str, list[str]]], histories: dict[str, pd.DataFrame]
) -> dict[tuple[str, str], pd.Series]:
    """只对实际在某个 state 分组里共同出现过的因子对算一次截面相关序列——不是候选因子全集
    的笛卡尔积；12 个 state 各自的候选因子通常只有几个，真正要算的对比"全体候选因子两两
    组合"少得多。"""
    series_by_pair: dict[tuple[str, str], pd.Series] = {}
    for _, _, alphas in groups:
        available = [a for a in alphas if a in histories]
        for a, b in combinations(sorted(set(available)), 2):
            key = _pair_key(a, b)
            if key not in series_by_pair:
                series_by_pair[key] = rank_ic(histories[key[0]], histories[key[1]])
    return series_by_pair


def _low_sample(samples: int, all_samples: int) -> bool:
    if samples < LOW_SAMPLE_MIN_SAMPLES:
        return True
    if all_samples > 0 and (samples / all_samples) < LOW_SAMPLE_MIN_FRACTION:
        return True
    return False


def _conditional_stats(series: pd.Series, regime_column: pd.Series | None, state: str) -> dict:
    """把一条序列（因子自己的 ic_series，或两个因子之间的截面相关序列）按 `regime_column`
    分组，取 `state` 那一行的统计量；`regime_column=None` 表示不做 regime 切片，直接用
    全历史（对照组用）。
    """
    if regime_column is None:
        # 复用 `ic_summary()` 而不是手写 mean/std——它对 std~=0 的边界情况（完美稳定信号）
        # 有专门处理，直接返回 ±inf 而不是被当成 0/0 误判成 NaN，见 `sherpa/metrics/factor.py`。
        summary = ic_summary(series)
        clean = series.dropna()
        return {
            "samples": int(clean.shape[0]),
            "mean": summary.mean,
            "std": summary.std,
            "ic_ir": summary.ic_ir,
            "low_sample": False,
        }

    table = conditional_ic_summary(series, regime_column)
    if state not in table.index:
        # 理论上不该发生：state 名字应该来自 regime_report() 本身产出的取值。真的发生
        # 说明 config.py 里这个维度下的 state 名字拼错了，显式报错而不是悄悄产出空行。
        raise KeyError(f"state {state!r} 在 regime[{regime_column.name!r}] 的实际取值里不存在: {list(table.index)}")
    row = table.loc[state]
    all_row = table.loc["ALL"]
    samples = int(row["samples"]) if not pd.isna(row["samples"]) else 0
    all_samples = int(all_row["samples"]) if not pd.isna(all_row["samples"]) else 0
    return {
        "samples": samples,
        "mean": row["ic_mean"],
        "std": row["ic_std"],
        "ic_ir": row["ic_ir"],
        "low_sample": _low_sample(samples, all_samples),
    }


def _safe_abs(value: float) -> float:
    """`ic_ir` 可能是 NaN——排序/挑代表因子时要让它稳居末位，而不是让 `abs(nan)` 参与
    比较产生未定义顺序。"""
    return abs(value) if not pd.isna(value) else -1.0


def main() -> None:
    for module_path in EXTRA_IMPORTS:
        importlib.import_module(module_path)

    groups = _groups()
    if not groups:
        raise SystemExit("config.REGIME_ALPHA_SETS 是空的，至少要给 12 个 regime 状态里的一部分配置候选因子")

    all_names = _all_referenced_alphas(groups)
    print(f"配置里一共引用了 {len(all_names)} 个不同因子，覆盖 {len(groups)} 个 (dimension, state) 分组")

    print("\n正在从 ClickHouse 拉取全市场数据……")
    panel = load_universe_panel()
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 {panel.interval} bar")

    forward_returns = label_forward_returns(panel)
    print(f"IC 标签：持有 {HORIZON_BARS} 根 bar、执行延迟 {EXECUTION_DELAY_BARS} 根 bar（research_config.json 的 label 一节）")

    print("正在计算可流通性掩码（剔除上线了但没有真实流动性的 symbol）……")
    mask = tradable_mask(panel.quote_volume, panel.trades_count)
    forward_returns = forward_returns.where(mask)

    print("正在计算 regime 打标（跟 regime_factor_report 体检同一套 regime_screening.regime_report）……")
    regime = regime_report(panel, benchmark_symbol=REGIME_BENCHMARK_SYMBOL)

    print("正在计算中性化用的风险暴露矩阵（Beta 对 REGIME_BENCHMARK_SYMBOL / Size 用 log(quote_volume)）……")
    exposures = default_style_exposures(panel, benchmark_symbol=REGIME_BENCHMARK_SYMBOL)

    print("正在计算候选因子历史分数（残差化后）……")
    histories, errors = _resolve_histories(all_names, panel, mask, exposures)
    if errors:
        print(f"  跳过 {len(errors)} 个算不出来的因子（占位实现）：{list(errors)}")
    groups = [(dim, state, [a for a in alphas if a in histories]) for dim, state, alphas in groups]

    print("正在计算每个因子自身相对未来收益的 ic_series（一次性算完，后面按 regime 条件切片复用）……")
    own_ic_series = {name: rank_ic(history, forward_returns) for name, history in histories.items()}

    print("正在计算候选因子两两之间的截面 Spearman 相关时序（一次性算完，后面按 regime 条件切片复用）……")
    pair_series = _needed_pair_series(groups, histories)
    print(f"  共 {len(pair_series)} 对不重复的因子组合")

    pair_rows = []
    cluster_rows = []
    for dimension, state, alphas in groups:
        if not alphas:
            print(f"  [跳过] {dimension}.{state} 没有可用因子")
            continue
        if len(alphas) == 1:
            # 只有 1 个候选时没有"对"可以算相关，但它也不可能跟谁冗余——照常走下面的流程（自成
            # 一簇、keep），让它出现在 02_regime_cluster_assignments.csv 里。下游关卡2 只读这份
            # CSV 取 keep 名单，如果这里直接跳过，这个 state 在下游就会凭空消失。
            print(f"  [提示] {dimension}.{state} 只有 1 个可用因子，无需去冗余，直接保留")

        regime_column = None if dimension == UNCONDITIONAL_DIMENSION else regime[dimension]

        own_stats = {name: _conditional_stats(own_ic_series[name], regime_column, state) for name in alphas}

        pairwise_corr: dict[tuple[str, str], float] = {}
        for a, b in combinations(alphas, 2):
            series = pair_series[_pair_key(a, b)]
            stats = _conditional_stats(series, regime_column, state)
            pairwise_corr[(a, b)] = stats["mean"]
            pair_rows.append(
                {
                    "dimension": dimension,
                    "state": state,
                    "alpha_a": a,
                    "alpha_b": b,
                    "samples": stats["samples"],
                    "corr_mean": stats["mean"],
                    "corr_std": stats["std"],
                    "abs_corr_mean": abs(stats["mean"]) if not pd.isna(stats["mean"]) else float("nan"),
                    "high_correlation": bool((not pd.isna(stats["mean"])) and abs(stats["mean"]) >= CORRELATION_THRESHOLD),
                    "low_sample": stats["low_sample"],
                }
            )

        cluster_of = cluster_by_correlation(alphas, pairwise_corr, CORRELATION_THRESHOLD)
        members_by_cluster: dict[int, list[str]] = {}
        for name, cluster_id in cluster_of.items():
            members_by_cluster.setdefault(cluster_id, []).append(name)

        for name in alphas:
            cluster_id = cluster_of[name]
            members = members_by_cluster[cluster_id]
            # 簇内代表因子 = 该 state 切片内 |own_ic_ir| 最大的那个（信噪比最高），
            # 跟 `regime_factor_report.py` 判断因子强度用的同一套标准，只是这里限定在
            # 当前 state 的历史切片内比较，而不是全历史。
            representative = max(members, key=lambda member: _safe_abs(own_stats[member]["ic_ir"]))
            own = own_stats[name]
            is_representative = name == representative
            cluster_rows.append(
                {
                    "dimension": dimension,
                    "state": state,
                    "qualified_name": name,
                    "cluster_id": cluster_id,
                    "cluster_size": len(members),
                    "cluster_members": " | ".join(members),
                    "own_ic_mean": own["mean"],
                    "own_ic_std": own["std"],
                    "own_ic_ir": own["ic_ir"],
                    "own_samples": own["samples"],
                    "own_low_sample": own["low_sample"],
                    "is_representative": is_representative,
                    "recommendation": "keep" if is_representative else "drop_redundant",
                    "redundant_with": "" if is_representative else representative,
                }
            )

    pairs_df = pd.DataFrame(pair_rows).sort_values(
        ["dimension", "state", "abs_corr_mean"], ascending=[True, True, False], na_position="last"
    )
    clusters_df = pd.DataFrame(cluster_rows)
    if not clusters_df.empty:
        clusters_df["own_abs_ic_ir"] = clusters_df["own_ic_ir"].apply(_safe_abs)
        clusters_df = clusters_df.sort_values(
            ["dimension", "state", "cluster_id", "own_abs_ic_ir"],
            ascending=[True, True, True, False],
        ).drop(columns=["own_abs_ic_ir"])

    _RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    pairs_df.to_csv(PAIRS_PATH, index=False)
    clusters_df.to_csv(CLUSTERS_PATH, index=False)

    n_dropped = int((clusters_df["recommendation"] == "drop_redundant").sum()) if not clusters_df.empty else 0
    print(f"\n共产出 {len(clusters_df)} 行按 (dimension, state) 切片的因子归属结果，其中建议剔除 {n_dropped} 处冗余。")
    print(f"结果已写入：\n  {PAIRS_PATH}\n  {CLUSTERS_PATH}")


if __name__ == "__main__":
    main()
