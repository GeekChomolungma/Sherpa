# research/ 目录地图

`research/` 目前只覆盖 [`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`](../QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md)
全生命周期的前两段——**阶段一：单因子挖掘与体检 (Alpha Research)** 和紧接其后的
**桥梁关卡：三大工程关卡 (The 3 Gates)**。阶段二（投资组合回测）、阶段三（纸面交易）、
阶段四（小资金实盘）不会挪进 `research/` 下面的子文件夹——按计划它们会各自开一个跟
`research/` 平级的顶层目录（比如未来的 `portfolio/`、`staging/`），因为那几个阶段跑的是
"用已经通过体检+关卡的因子构建/运行真实组合"，跟这里"因子还在被检验/去冗余"的探索性质不是
一回事，放在同一棵目录树下容易让人以为它们是同一套产线的延续。等那些目录真正开出来，会在
这里补一条指向它们的链接；目前阶段一 + 关卡1 有实际内容，关卡2 处于设计阶段（只有执行文档）。

## 一键跑全流程

仓库根目录的 [`run_research.sh`](../run_research.sh) 按依赖顺序把阶段一到关卡1 串起来跑
（regime 打标 → 全局筛选 → regime 条件体检 → 汇总报告 → 正交化），失败立刻停下并提示怎么续跑：

```bash
export CH_HOST=... CH_PASSWORD=...
bash run_research.sh --dry-run                # 先看一遍要跑哪些命令
bash run_research.sh --refresh-candidates     # 正式跑，并用新的 04 矩阵 Top5 刷新正交化候选池
bash run_research.sh --from-step 4            # 某一步失败修好后，从第 4 步继续
bash run_research.sh --refresh-candidates --refresh-synthesis-candidates
                                              # 一路跑到关卡2 入口：关卡1 的 keep 名单写进 factor_synthesis/config.py
```

可选步骤（`--with-calibration` 流动性掩码校准、`--with-vectorized` 单因子迷你回测）和全部参数见脚本开头的说明。

**跑完怎么读结果、怎么下结论**：见 [`RESULT_READING_GUIDE.md`](RESULT_READING_GUIDE.md)。

## 统一研究配置：时间窗、holdout、IC 标签

所有子项目共用一份 [`research_config.json`](research_config.json)，按用途分节，以后有新的跨子项目
研究配置就再加一节：

**`window`：取数区间与样本外 holdout**

| 字段 | 当前值 | 含义 |
|---|---|---|
| `interval` | `4h` | K 线周期 |
| `research_start` ~ `validation_start` | `2020-01-01` ~ `2024-09-15` | **选择段**：阶段一体检、关卡1 去冗余只在这一段上做（这几个子目录的 `data.py` 取数截止到 `validation_start`）；关卡2 在这一段上估计因子方向 |
| `validation_start` ~ `research_end` | `2024-09-15` ~ `2026-03-15` | **验证段**：关卡2 比较各合成方案。对"选因子"来说是没见过的数据，比较才公平 |
| `research_end` ~ `holdout_end` | `2026-03-15` ~ `2026-09-15` | **样本外 holdout**：任何筛选、调参都不碰，只在关卡2 定稿后做一次性验收 |

选择段 + 验证段合称**研究段**（`research_start ~ research_end`）。为什么要把研究段再切一刀：候选因子是在
选择段上挑出来的，如果关卡2 还在同一段上比较合成方案，就是"在考自己出的题"，而且自由度越大的方案
（按 regime 各挑一套）虚高得越多。详见 `factor_synthesis/README.md` §6.0。

**`label`：IC 检验用的"未来收益"标签口径**

| 字段 | 当前值 | 含义 |
|---|---|---|
| `horizon_bars` | `1` | 持有期：收益累计几根 bar |
| `execution_delay_bars` | `0` | 执行延迟：信号在 bar t 收盘算出后，晚几根 bar 才按收盘价成交 |

t 行的标签 = 从 `close[t + delay]` 持有到 `close[t + delay + horizon]` 的收益
（`sherpa.metrics.factor.forward_returns`）。默认值等价于历史写法 `close.pct_change().shift(-1)`；
`execution_delay_bars = 1` 等价于 `shift(-2)`，用来检验信号是不是只在"收盘后立刻成交"那一瞬间有效
（短周期反转因子的 IC 里常混有买卖价差来回跳的成分，实盘吃不到，延迟一根 bar 后会大幅消失）。

各子目录的 `data.py` 把配置读成常量（`INTERVAL`/`START_TIME`/`END_TIME`，以及 `HORIZON_BARS`/
`EXECUTION_DELAY_BARS`），并提供 `label_forward_returns(panel)` 统一构造标签。阶段一体检、
`run_screening`、关卡1 挑代表因子都用它，所以**改一处配置，整条链的 IC 口径一起变**。

为什么要统一：阶段一在哪段历史、用哪种标签选出因子，关卡1 就必须在同一段历史、同一种标签上检验
冗余和挑代表，否则两边结论对不上（统一之前，阶段一从 2024 开始、关卡1 从 2020 开始）。这是
"子目录之间不共享代码、不共享中间结果"原则的唯一例外：共享的是一份配置，不是代码或产出。

- 想整体换区间或标签口径：只改 `research_config.json`，改完要从阶段一开始整条链重跑
  （`run_research.sh --refresh-candidates --refresh-synthesis-candidates`）；
- **对比两种口径**（比如延迟 0 和延迟 1）：结果文件会被覆盖，跑第二版之前先把 `results/` 等产出复制一份；
- 想临时换一次区间做实验：调用 `load_universe_panel(start_time=..., end_time=...)` 显式传参，不要改 JSON；
- holdout 的用法规矩和预热（warm-up）注意事项见
  [`factor_synthesis/README.md`](factor_synthesis/README.md) §6.4。**不要把 `research_end` 往后挪来"多用点数据"**，
  那等于把 holdout 废掉。

## 子目录 -> 生命周期阶段 对照表

| 子目录 | 生命周期阶段 | 角色 |
|---|---|---|
| [`alpha_research/`](alpha_research/) | 阶段一：单因子挖掘与体检 | 按因子家族分子目录（目前只有 `worldquant_101/`），每个家族自己的完整体检产线：第一层全局筛选、第二层向量化回测、regime 条件画像，均已接入中性化残差化（先剔除 Beta/Size 被动暴露，再算 IC）。新家族（TradingView、自定义）以后按同样结构加子目录进来。 |
| [`tradability_calibration/`](tradability_calibration/) | 阶段一的支撑基建校准 | 不属于任何具体因子家族，是横切的超参数研究：给 `sherpa.metrics.tradability.tradable_mask` 的 `min_percentile`/`min_quote_volume`/`min_trades_count` 做数据驱动校准，供 `alpha_research/` 下所有家族的体检复用。 |
| [`regime_factor_report/`](regime_factor_report/) | 阶段一产出的解读/汇总层 | 通用 CLI 工具，把任意家族产出的 regime 条件 IC 长表（比如 `alpha_research/worldquant_101/regime_alpha_profile.csv`）转成人类可读的分类报告、维度宽表、状态排行榜、`04_regime_matrix.csv` 这张 12-state 作战矩阵。 |
| [`factor_orthogonalization/`](factor_orthogonalization/) | 桥梁关卡 · 关卡1：因子相关性分析与正交化 | 对手动圈定的候选因子池（同样先中性化残差化），在每个 regime state 自己的历史切片内做截面相关聚类，标记冗余因子、推荐每簇保留信噪比最高的代表因子。以后新因子的增量检验规划见 [`INCREMENTAL_TODO.md`](factor_orthogonalization/INCREMENTAL_TODO.md)。 |
| [`factor_synthesis/`](factor_synthesis/) | 桥梁关卡 · 关卡2：基于 Regime 的动态多因子合成 | **设计阶段**，已有入口：`refresh_candidates.py` 把关卡1 `02_regime_cluster_assignments.csv` 里 keep 的因子写进 `config.py` 的 `REGIME_FACTOR_SETS`（`run_research.sh --refresh-synthesis-candidates`，步骤 8）。合成方案：等权 / ICIR 基线 → Regime 路由 → 平滑，walk-forward 样本外比较，holdout 一次性验收，见 [`README.md`](factor_synthesis/README.md)。 |
| [`REGIME_FRAMEWORK_GUIDE.md`](REGIME_FRAMEWORK_GUIDE.md) | 阶段一理论指导 | 市场状态分类的方法论文档，不是代码目录：TradFi 四大维度到 Crypto 的映射、加密永续特有维度、Python 落地方式。 |
| [`REGIME_ALPHA_EVALUATION_WORKFLOW.md`](REGIME_ALPHA_EVALUATION_WORKFLOW.md) | 阶段一理论指导 | 因子体检工作流 SOP：为什么不能物理切片数据、Point-in-time 条件掩码打标规范、决策分类矩阵。 |

风险与风格中性化原本是独立的"关卡2"，经讨论确认必须前移并入阶段一（详见
`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2 的顺序结论），已经落地在 `sherpa.risk`
（`exposure.rolling_beta`/`neutralize.neutralize`）+ `sherpa.backtest.style_exposure`，
并接入了上面 `alpha_research/`、`factor_orthogonalization/` 的各个脚本——不是 `research/`
下的独立子目录，而是内嵌进阶段一各产线的一个处理步骤。关卡2（基于 Regime 的动态多因子合成）已经开了
`factor_synthesis/` 目录，目前只有执行文档；关卡3（换手摩擦压力测试）在 `research/` 下还没有
对应子目录，等真正开始做才会在这里加对应目录并更新这张表。

## 一个具体研究项目该放哪：判断口诀

1. **是不是在检验某个具体因子家族本身**（算不算得出来、第一层 IC_IR 过不过关、regime
   下条件表现如何）？是 -> 放进 `alpha_research/<家族名>/`。
2. **是不是在给某个跨家族都要用的基建组件调超参数**（不产出任何 alpha 相关结论，只关心
   基建本身的行为）？是 -> 单独开一个跟 `alpha_research/` 平级的顶层目录（参考
   `tradability_calibration/` 的先例）。
3. **是不是在把已有的体检产出转换成另一种人类/策略层更容易消费的格式**，本身不引入新的
   统计判断？是 -> 单独开一个跟 `alpha_research/` 平级的顶层目录（参考
   `regime_factor_report/` 的先例）。
4. **是不是在解决"多个已经体检过的因子放在一起会不会有问题"**（相关性、动态权重、摩擦
   成本——注意风险暴露中性化不算在内，那一步已经并入阶段一，不是独立关卡）？是 -> 对应
   关卡几，就在 `research/` 下开一个平级的关卡目录（参考 `factor_orthogonalization/`
   对应关卡1的先例）。

这四类之间刻意不共享中间结果文件（各自的 `README.md` 里都写了具体原因）：候选池、参数、
CSV 中间产出都在各自子目录内部闭环，跨子目录之间通过手动配置（比如
`factor_orthogonalization/config.py` 手写候选因子名单）而不是自动读文件来传递信息，避免
一个子目录改了输出格式就连锁弄坏另一个子目录。
