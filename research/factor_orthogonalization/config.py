"""手动配置：本轮参与正交化聚类分析的候选因子池——按 12 个 regime 状态分别指定。

`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §4 关卡2（基于微观 Regime 的动态多因子合成）最终是
"regime 命中 state X 时，从属于 X 的因子集合里挑权重"，所以关卡1 的正交化检验也必须限定在
同一个 regime 历史切片里做——两个因子如果全历史看不太相关，但恰好都是"trend=bull 专属
强因子"，会一起被装进同一个 state 的因子集合里，那就必须在 trend=bull 这段历史上专门检验
它们两个是否冗余,而不是看一个跟 regime 无关的全局相关系数。

因子名一律是 registry 的 qualified_name（`"{family}.{name}"`，参见
`sherpa.alpha.base.Alpha.qualified_name`），worldquant / tradingview / custom 三大家族都
能混用。新家族/自定义模块的接入方式见下面 `EXTRA_IMPORTS` 的说明。
"""

from __future__ import annotations

# 12 个 regime 状态各自的候选因子集：{dimension: {state: [qualified_name, ...]}}。
#
# 维度名与 state 取值必须跟 `sherpa.backtest.regime_screening.regime_report()`（即
# `sherpa.metrics.regime.build_regime_report()`）打出来的列名/取值完全一致，否则运行时会
# 在对应分组直接报错（找不到这个 state）：
#     trend       -> bull / bear / neutral
#     volatility  -> high / normal / low
#     dispersion  -> high / normal / low
#     liquidity   -> high / normal / starved
#
# 下面的值是从 `research/regime_factor_report/results/04_regime_matrix.csv`（残差化版本，
# 由 `run_alpha_regime_profile.py`（`USE_NEUTRALIZATION=True`）→ `regime_factor_report.py`
# 产出）里每个 state 的 Top5 alpha 抄过来的——不是原始分数版本（`04_regime_matrix_without_neutral.csv`），
# 已经是剥离过 Beta/Size 暴露之后的排行榜，正好用来验证一个直觉：同一个 state 排行榜前几名
# 之间是不是其实在重复下注同一份信息。按需替换成你自己想测试的候选因子。
#
# `trend.bull` 只有 54 个样本（占该维度 ALL 样本的 ~6%），`04_regime_matrix.csv` 里
# `low_sample=True`——这个 state 的排行榜可信度比其余 11 个低，解读这里的聚类结果时要打
# 折扣，不能跟其它样本充足的 state 同等看待。
REGIME_ALPHA_SETS: dict[str, dict[str, list[str]]] = {
    "trend": {
        "bull": [
            "worldquant.alpha088",
            "worldquant.alpha054",
            "worldquant.alpha003",
            "worldquant.alpha010",
            "worldquant.alpha068",
        ],
        "bear": [
            "worldquant.alpha088",
            "worldquant.alpha016",
            "worldquant.alpha044",
            "worldquant.alpha050",
            "worldquant.alpha027",
        ],
        "neutral": [
            "worldquant.alpha016",
            "worldquant.alpha013",
            "worldquant.alpha088",
            "worldquant.alpha050",
            "worldquant.alpha015",
        ],
    },
    "volatility": {
        "high": [
            "worldquant.alpha016",
            "worldquant.alpha050",
            "worldquant.alpha088",
            "worldquant.alpha027",
            "worldquant.alpha013",
        ],
        "normal": [
            "worldquant.alpha016",
            "worldquant.alpha044",
            "worldquant.alpha088",
            "worldquant.alpha050",
            "worldquant.alpha013",
        ],
        "low": [
            "worldquant.alpha016",
            "worldquant.alpha088",
            "worldquant.alpha050",
            "worldquant.alpha013",
            "worldquant.alpha015",
        ],
    },
    "dispersion": {
        "high": [
            "worldquant.alpha016",
            "worldquant.alpha013",
            "worldquant.alpha088",
            "worldquant.alpha015",
            "worldquant.alpha050",
        ],
        "normal": [
            "worldquant.alpha088",
            "worldquant.alpha016",
            "worldquant.alpha050",
            "worldquant.alpha044",
            "worldquant.alpha015",
        ],
        "low": [
            "worldquant.alpha016",
            "worldquant.alpha013",
            "worldquant.alpha088",
            "worldquant.alpha050",
            "worldquant.alpha044",
        ],
    },
    "liquidity": {
        "high": [
            "worldquant.alpha088",
            "worldquant.alpha053",
            "worldquant.alpha050",
            "worldquant.alpha016",
            "worldquant.alpha027",
        ],
        "normal": [
            "worldquant.alpha016",
            "worldquant.alpha088",
            "worldquant.alpha044",
            "worldquant.alpha013",
            "worldquant.alpha050",
        ],
        "starved": [
            "worldquant.alpha016",
            "worldquant.alpha038",
            "worldquant.alpha050",
            "worldquant.alpha015",
            "worldquant.alpha013",
        ],
    },
}

# 可选：不区分 regime、直接用全历史算的对照组。默认空列表即跳过——只有显式填了才会额外
# 产出一组 `dimension=unconditional, state=ALL` 的结果行，用来对比"某对因子是只在特定
# regime 下冗余，还是从头到尾都冗余"这两种情况（后者说明这对因子的重复关系更根本，换个
# regime 也大概率还是冗余）。
UNCONDITIONAL_ALPHAS: list[str] = []

# 新家族/自定义模块接入：worldquant / tradingview / custom 三个内置家族已经在
# `run_orthogonalization.py` 里统一 import 触发 `@register_alpha` 注册，这里不用管。如果
# 因子定义在这三个包之外的某个模块里，把该模块的可 import 路径加进来，脚本启动时会自动
# `importlib.import_module()` 一遍触发注册，之后就能在上面按 qualified_name 引用它。
EXTRA_IMPORTS: list[str] = [
    # "my_project.custom_alphas",
]

# 两个因子在某个 state 切片内的截面相关均值 |corr_mean| 达到这个阈值，就判定它们在这个 state
# 下冗余——四大关卡·关卡1 的核心判据。0.7 是常见的经验起点，不是理论最优值：具体项目应该
# 结合 `results/01_regime_factor_correlation_pairs.csv` 里实际的相关性分布去调整。
CORRELATION_THRESHOLD: float = 0.7

# 透传给 `sherpa.backtest.regime_screening.regime_report()` 的大盘锚点——要跟
# `regime_factor_report`/`alpha_research/worldquant_101` 那批体检用的基准一致，才能让这里聚类出的 state
# 跟 `04_regime_matrix.csv` 里说的是同一件事。
REGIME_BENCHMARK_SYMBOL: str = "BTCUSDT"

# 跟 `regime_factor_report.py` 同一套 low-sample 保护红线：某个 (dimension, state) 切片
# 的样本数太少时，聚类结果/代表因子选择可能只是噪音，输出里会把对应行标记为 low_sample，
# 而不是自动改动或剔除它——保留原结果 + 显式风险标记，跟阶段一体检的处理方式一致。
LOW_SAMPLE_MIN_SAMPLES: int = 100
LOW_SAMPLE_MIN_FRACTION: float = 0.10
