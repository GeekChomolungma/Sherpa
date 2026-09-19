# research/ 目录地图

`research/` 目前只覆盖 [`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`](../QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md)
全生命周期的前两段——**阶段一：单因子挖掘与体检 (Alpha Research)** 和紧接其后的
**桥梁关卡：四大工程关卡 (The 4 Gates)**。阶段二（投资组合回测）、阶段三（纸面交易）、
阶段四（小资金实盘）不会挪进 `research/` 下面的子文件夹——按计划它们会各自开一个跟
`research/` 平级的顶层目录（比如未来的 `portfolio/`、`staging/`），因为那几个阶段跑的是
"用已经通过体检+关卡的因子构建/运行真实组合"，跟这里"因子还在被检验/去冗余"的探索性质不是
一回事，放在同一棵目录树下容易让人以为它们是同一套产线的延续。等那些目录真正开出来，会在
这里补一条指向它们的链接；目前只有阶段一 + 关卡1 有实际内容。

## 子目录 -> 生命周期阶段 对照表

| 子目录 | 生命周期阶段 | 角色 |
|---|---|---|
| [`alpha_research/`](alpha_research/) | 阶段一：单因子挖掘与体检 | 按因子家族分子目录（目前只有 `worldquant_101/`），每个家族自己的完整体检产线：第一层全局筛选、第二层向量化回测、regime 条件画像。新家族（TradingView、自定义）以后按同样结构加子目录进来。 |
| [`tradability_calibration/`](tradability_calibration/) | 阶段一的支撑基建校准 | 不属于任何具体因子家族，是横切的超参数研究：给 `sherpa.metrics.tradability.tradable_mask` 的 `min_percentile`/`min_quote_volume`/`min_trades_count` 做数据驱动校准，供 `alpha_research/` 下所有家族的体检复用。 |
| [`regime_factor_report/`](regime_factor_report/) | 阶段一产出的解读/汇总层 | 通用 CLI 工具，把任意家族产出的 regime 条件 IC 长表（比如 `alpha_research/worldquant_101/regime_alpha_profile.csv`）转成人类可读的分类报告、维度宽表、状态排行榜、`04_regime_matrix.csv` 这张 12-state 作战矩阵。 |
| [`factor_orthogonalization/`](factor_orthogonalization/) | 桥梁关卡 · 关卡1：因子相关性分析与正交化 | 对手动圈定的候选因子池，在每个 regime state 自己的历史切片内做截面相关聚类，标记冗余因子、推荐每簇保留信噪比最高的代表因子。 |
| [`REGIME_FRAMEWORK_GUIDE.md`](REGIME_FRAMEWORK_GUIDE.md) | 阶段一理论指导 | 市场状态分类的方法论文档，不是代码目录：TradFi 四大维度到 Crypto 的映射、加密永续特有维度、Python 落地方式。 |
| [`REGIME_ALPHA_EVALUATION_WORKFLOW.md`](REGIME_ALPHA_EVALUATION_WORKFLOW.md) | 阶段一理论指导 | 因子体检工作流 SOP：为什么不能物理切片数据、Point-in-time 条件掩码打标规范、决策分类矩阵。 |

关卡2（风险与风格中性化）、关卡3（基于 Regime 的动态多因子合成）、关卡4（换手摩擦压力测试）
目前在 `research/` 下还没有对应子目录——按 `QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §4
的说法，这几关的实操指南是"预留规划中"，等真正开始做才会在这里加对应目录并更新这张表。

## 一个具体研究项目该放哪：判断口诀

1. **是不是在检验某个具体因子家族本身**（算不算得出来、第一层 IC_IR 过不过关、regime
   下条件表现如何）？是 -> 放进 `alpha_research/<家族名>/`。
2. **是不是在给某个跨家族都要用的基建组件调超参数**（不产出任何 alpha 相关结论，只关心
   基建本身的行为）？是 -> 单独开一个跟 `alpha_research/` 平级的顶层目录（参考
   `tradability_calibration/` 的先例）。
3. **是不是在把已有的体检产出转换成另一种人类/策略层更容易消费的格式**，本身不引入新的
   统计判断？是 -> 单独开一个跟 `alpha_research/` 平级的顶层目录（参考
   `regime_factor_report/` 的先例）。
4. **是不是在解决"多个已经体检过的因子放在一起会不会有问题"**（相关性、风险暴露、动态
   权重、摩擦成本）？是 -> 对应关卡几，就在 `research/` 下开一个平级的关卡目录（参考
   `factor_orthogonalization/` 对应关卡1的先例）。

这四类之间刻意不共享中间结果文件（各自的 `README.md` 里都写了具体原因）：候选池、参数、
CSV 中间产出都在各自子目录内部闭环，跨子目录之间通过手动配置（比如
`factor_orthogonalization/config.py` 手写候选因子名单）而不是自动读文件来传递信息，避免
一个子目录改了输出格式就连锁弄坏另一个子目录。
