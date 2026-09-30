# research/ 目录地图

`research/` 目前只覆盖 [`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`](../QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md)
全生命周期的前两段——**阶段一：单因子挖掘与体检 (Alpha Research)** 和紧接其后的
**桥梁关卡：三大工程关卡 (The 3 Gates)**。阶段二（投资组合回测）、阶段三（纸面交易）、
阶段四（小资金实盘）不会挪进 `research/` 下面的子文件夹——按计划它们会各自开一个跟
`research/` 平级的顶层目录（比如未来的 `portfolio/`、`staging/`），因为那几个阶段跑的是
"用已经通过体检+关卡的因子构建/运行真实组合"，跟这里"因子还在被检验/去冗余"的探索性质不是
一回事，放在同一棵目录树下容易让人以为它们是同一套产线的延续。等那些目录真正开出来，会在
这里补一条指向它们的链接；目前阶段一 + 关卡1 有实际内容，关卡2 处于设计阶段（只有执行文档）。

## 一键跑全流程：按研究线（track）

研究按**研究线**组织：每条研究线在 `alpha_research/<track>/` 下有自己的 `track.json`（因子范围、处理链、regime
维度、关卡1/2 真跑还是透传）和编排脚本 `run_track.sh`，整条流水线的产出都归档在研究线目录下。说明见
[`alpha_research/README.md`](alpha_research/README.md)。

```bash
export CH_HOST=... CH_PASSWORD=...
bash research/alpha_research/worldquant_101/run_track.sh --dry-run   # 先看一遍要跑哪些命令
bash research/alpha_research/worldquant_101/run_track.sh             # 世坤101 全流程（阶段一 -> 关卡1/2/3）
bash research/alpha_research/worldquant_101/run_track.sh --from-step 3   # 某一步失败修好后，从关卡1 继续
bash research/alpha_research/custom_starter/run_track.sh             # 自定义因子研究线（关卡1/2 透传）
```

根目录的 [`run_research.sh`](../run_research.sh) 是兼容入口，转发到 `worldquant_101/run_track.sh`。可选步骤
（`--with-calibration` 流动性掩码校准）和全部参数
见各 `run_track.sh` 开头的说明。

**跑完怎么读结果、怎么下结论**：见 [`RESULT_READING_GUIDE.md`](RESULT_READING_GUIDE.md)。

## 统一研究配置：时间窗、holdout、IC 标签、大盘锚点、交易成本

所有子项目共用一份 [`research_config.json`](research_config.json)，按用途分节，以后有新的跨子项目
研究配置就再加一节。**具体取值以 JSON 为准**（这里只解释含义，不抄数值，免得文档过期）；
各研究线的 `run_track.sh` 启动时会把整份配置打印出来。

**`window`：取数区间与样本外 holdout**

| 字段 | 含义 |
|---|---|
| `interval` | K 线周期 |
| `research_start` ~ `validation_start` | **选择段**：阶段一体检、关卡1 去冗余只在这一段上做（这几个子目录的 `data.py` 取数截止到 `validation_start`）；关卡2 在这一段上估计因子方向和权重 |
| `validation_start` ~ `research_end` | **验证段**：关卡2 比较各合成方案。对"选因子"来说是没见过的数据，比较才公平 |
| `research_end` ~ `holdout_end` | **样本外 holdout**：任何筛选、调参都不碰，只在关卡2 定稿后做一次性验收 |

选择段 + 验证段合称**研究段**（`research_start ~ research_end`）。为什么要把研究段再切一刀：候选因子是在
选择段上挑出来的，如果关卡2 还在同一段上比较合成方案，就是"在考自己出的题"，而且自由度越大的方案
（按 regime 各挑一套）虚高得越多。详见 `factor_synthesis/README.md` §6.0。

**`label`：IC 检验用的"未来收益"标签口径**

| 字段 | 含义 |
|---|---|
| `horizon_bars` | 持有期：收益累计几根 bar |
| `execution_delay_bars` | 执行延迟：信号在 bar t 收盘算出后，晚几根 bar 才按收盘价成交 |

t 行的标签 = 从 `close[t + delay]` 持有到 `close[t + delay + horizon]` 的收益
（`sherpa.metrics.factor.forward_returns`）。默认值等价于历史写法 `close.pct_change().shift(-1)`；
`execution_delay_bars = 1` 等价于 `shift(-2)`，用来检验信号是不是只在"收盘后立刻成交"那一瞬间有效
（短周期反转因子的 IC 里常混有买卖价差来回跳的成分，实盘吃不到，延迟一根 bar 后会大幅消失）。

**`market`：大盘锚点**

| 字段 | 含义 |
|---|---|
| `benchmark_symbol` | regime 打标的趋势锚点，同时也是 Beta 暴露（中性化剥离的对象）的基准。各关必须一致，否则 state 的含义、残差的口径都对不上 |

**`costs`：交易成本口径**（目前只有关卡3 `friction_test/` 读它）

| 字段 | 含义 |
|---|---|
| `venue` | 交易所 / 市场，只作标注 |
| `maker_fee_bps` / `taker_fee_bps` | 挂单 / 吃单手续费（bps，1 bp = 0.01%），按当前会员档位填 |
| `taker_slippage_bps` | 吃单的常规滑点假设 |
| `stress_slippage_bps` | 压力测试用的大滑点假设 |

换会员档位或换交易所只改这一节。关卡3 用它构造全 maker / 全 taker / 压力三种成本模型，见
`friction_test/README.md` §3。

各子目录的 `data.py` 把配置读成常量（`INTERVAL`/`START_TIME`/`END_TIME`、`HORIZON_BARS`/
`EXECUTION_DELAY_BARS`、`BENCHMARK_SYMBOL`），并提供 `label_forward_returns(panel)` 统一构造标签。
阶段一体检、关卡1 挑代表因子、关卡2 评估合成分数都用它们，所以**改一处配置，
整条链的口径一起变**。研究脚本里不要再直接写 `"BTCUSDT"` 这类常量，也不要依赖 `sherpa` 函数的
默认锚点参数——一律显式传 `BENCHMARK_SYMBOL`。

为什么要统一：阶段一在哪段历史、用哪种标签选出因子，关卡1 就必须在同一段历史、同一种标签上检验
冗余和挑代表，否则两边结论对不上（统一之前，阶段一从 2024 开始、关卡1 从 2020 开始）。这是
"子目录之间不共享代码、不共享中间结果"原则的唯一例外：共享的是一份配置，不是代码或产出。

- 想整体换区间或标签口径：只改 `research_config.json`，改完要从阶段一开始把每条研究线整条重跑；
- **对比两种口径**（比如延迟 0 和延迟 1）：结果文件会被覆盖，跑第二版之前先把研究线的 `results/`、`handoff/` 复制一份；
- 想临时换一次区间做实验：调用 `load_universe_panel(start_time=..., end_time=...)` 显式传参，不要改 JSON；
- holdout 的用法规矩和预热（warm-up）注意事项见
  [`factor_synthesis/README.md`](factor_synthesis/README.md) §6.4。**不要把 `research_end` 往后挪来"多用点数据"**，
  那等于把 holdout 废掉。

## 模块接口表：各关之间靠什么连在一起

每一关都**自己从数据库取数、自己计算**，研究子目录之间不互相 import 业务代码、不读对方的明细产出。
它们之间的联系只有下面四类，改动任何一类都要按"影响范围"一栏检查。

### 1. 显性纽带：标准交接文件（handoff）

**生产者有义务按标准格式输出，消费者只认标准格式**（[`_shared/handoff.py`](_shared/handoff.py)）。每个阶段固定读
研究线里前一阶段的 `handoff/<阶段>.json`、写自己的那份；关卡1/2 可以按研究线设成透传（同样产出标准交接文件），
下游感知不到差别。以前那套"下游 refresh 脚本读上游明细 CSV、重写自己 config.py"的做法已经去掉。

| 上游（产出） | 交接物 | 下游（消费） |
|---|---|---|
| 阶段一 `alpha_research/_pipeline/run_profile.py <track>`（读库） | `<track>/regime_alpha_profile.csv`（长表；列 `alpha, dimension, state, samples, ic_mean, ic_std, ic_ir, win_rate, t_stat, p_value`，每个因子一行 `unconditional/ALL` 基线） | 汇总报告 |
| 汇总报告 `regime_factor_report.py --handoff-out`（不读库） | `handoff/report.json`：**候选集**（04/05 矩阵的显著 + \|IC_IR\| Top-K） | 关卡1 |
| 关卡1 `run_orthogonalization.py`（读库；透传时不读库） | `handoff/orthogonalization.json`：**候选集**（去冗余后的保留名单） | 关卡2 |
| 关卡2 `run_synthesis.py`（读库；透传时不读库） | `handoff/synthesis.json`：**配方集**（冻结的方向 / 权重，真跑时带验证段 `reference`） | 关卡3 |
| 关卡3 `run_friction.py`（读库） | `results/friction/00~03_*.csv` | 人工阅读、决策；选定的组合构建方式进阶段二 |

**改交接格式（`handoff.py` 的 schema）等于同时改了所有阶段的接口**，要升 `SCHEMA_VERSION`、跑
`tests/research/`，并把各研究线从阶段一整条重跑。各阶段的明细 CSV 列可以自由改，只要交接文件的格式不变，
下游不受影响。

### 2. 隐性纽带：共享配置 `research_config.json`

`window` / `label` / `market` 三节被所有读库的 `data.py` 读取（见上一节）。**改了它，整条链的结论
都会变，每条研究线都要从阶段一整体重跑**（比如 `worldquant_101/run_track.sh --from-step 3`）。

### 3. 隐性纽带：共用 `sherpa` 核心函数

各关分别调用同一批核心函数，**口径必须一致**，研究结论才前后对得上：

| 函数 | 作用 | 用到的关 |
|---|---|---|
| `sherpa.backtest.residual`（`ScorePreprocessor` / `residual_scores`），内部调 `tradable_mask` + `default_style_exposures` + `neutralize` | 原始分数 → 可交易掩码 → Beta / Size 中性化残差；IC 标签套同一个掩码 | 阶段一、关卡1、关卡2、关卡3 |
| `sherpa.backtest.regime_screening.regime_report` | regime 打标 | 阶段一、关卡1、关卡2 |
| `sherpa.metrics.factor.rank_ic` / `ic_summary` / `ic_significance` / `conditional_ic_summary` | IC 与显著性 | 阶段一、关卡1、关卡2 |
| `sherpa.metrics.factor.forward_returns`（经 `data.label_forward_returns`） | IC 标签 | 阶段一、关卡1、关卡2 |

所谓"解耦"是指研究子目录之间不共享代码和中间文件，**不是**各算各的逻辑。改这些核心函数等于同时改了
所有关卡，改完必须跑全部测试（`python -m pytest`），并从第 3 步整体重跑。

### 4. 隐性纽带：跨文件保持一致的约定

没有集中定义、需要人工保持一致的少数约定（改其中一处要全局搜索一起改）：

| 约定 | 出现位置 |
|---|---|
| regime 的维度名、state 名及顺序（`trend: bear/neutral/bull` …） | 唯一定义处 `sherpa.metrics.regime.REGIME_STATES` / `REGIME_DIMENSIONS`；`regime_factor_report.py` 的 `DEFAULT_STATE_ORDER`、track 配置的 `regime.dimensions` 都引用它（关卡2 的路由维度跟着候选集走）。打标函数里的 state 字符串改了要同步改这个常量（有测试校验） |
| 全历史基线的标记 `dimension=unconditional, state=ALL` | `sherpa.backtest.regime_screening.UNCONDITIONAL_DIMENSION`、`regime_factor_report.py`、关卡1 `run_orthogonalization.py`（交接文件里这组名单是候选集的 `global`） |
| `recommendation` 的取值（`keep` / `drop_redundant`，预留 `keep_complementary`） | 只在关卡1 `run_orthogonalization.py` 内部（`KEEP_RECOMMENDATIONS` 决定哪些进交接文件），下游不再读它 |

### 改动时的自查顺序

1. 只改某一关的内部逻辑 → 不影响别的关，重跑这一关及下游即可；
2. 改了某一关的明细 CSV → 不影响下游（下游只读交接文件）；改了交接格式 → 见第 1 类；
3. 改了 `research_config.json` 或 `sherpa` 核心函数 → 跑全部测试，每条研究线从阶段一整体重跑（第 2、3 类）；
4. 改了第 4 类约定 → 全局搜索，所有出现位置一起改。

## 子目录 -> 生命周期阶段 对照表

| 子目录 | 生命周期阶段 | 角色 |
|---|---|---|
| [`alpha_research/`](alpha_research/) | 阶段一：单因子挖掘与体检 | 按**研究线（track）**分子目录：每条线一份 `track.json`（因子范围、处理链开关、regime 维度）+ 自己的编排脚本，产出归档在自己目录下；共用的阶段一工具在 `_pipeline/`。整条流水线（阶段一 → 关卡3）的产出和阶段之间的交接文件都归档在研究线目录下。目前有 `worldquant_101/`（全流程样板）和 `custom_starter/`（自定义因子，关卡1/2 透传直达关卡3）。说明见 [`alpha_research/README.md`](alpha_research/README.md)。 |
| [`tradability_calibration/`](tradability_calibration/) | 阶段一的支撑基建校准 | 不属于任何具体因子家族，是横切的超参数研究：给 `sherpa.metrics.tradability.tradable_mask` 的 `min_percentile`/`min_quote_volume`/`min_trades_count` 做数据驱动校准，供 `alpha_research/` 下所有家族的体检复用。 |
| [`regime_factor_report/`](regime_factor_report/) | 阶段一产出的解读/汇总层 | 通用 CLI 工具，把任意家族产出的 regime 条件 IC 长表（比如 `alpha_research/worldquant_101/regime_alpha_profile.csv`）转成人类可读的分类报告、维度宽表、状态排行榜、`04_regime_matrix.csv` 这张 12-state 作战矩阵；`--handoff-out` 同时产出给关卡1 的候选集交接文件。 |
| [`factor_orthogonalization/`](factor_orthogonalization/) | 桥梁关卡 · 关卡1：因子相关性分析与正交化 | 读研究线的候选集交接文件（同样先中性化残差化），在每个 regime state 自己的历史切片内做截面相关聚类，标记冗余因子、推荐每簇保留信噪比最高的代表因子，保留名单写成候选集交给关卡2；可按研究线透传。以后新因子的增量检验规划见 [`INCREMENTAL_TODO.md`](factor_orthogonalization/INCREMENTAL_TODO.md)。 |
| [`factor_synthesis/`](factor_synthesis/) | 桥梁关卡 · 关卡2：基于 Regime 的动态多因子合成 | 读关卡1 的候选集交接文件，各合成方案在验证段上比较，全部方案 + 最强单因子冻结成配方集交给关卡3；可按研究线透传（候选集直接变成等权配方）。合成方案：等权 / ICIR 基线 → Regime 路由 → 平滑，walk-forward 样本外比较，holdout 一次性验收，见 [`README.md`](factor_synthesis/README.md)。 |
| [`friction_test/`](friction_test/) | 桥梁关卡 · 关卡3：换手摩擦与组合构建 | 读研究线的配方集交接文件（关卡2 的方案或它的透传），所有研究线都必须过；`run_friction.py` 对每个配方 × 权重映射（demean_l1 / Top-K）× 调仓频率跑 `run_vectorized_backtest`，在多种成本假设下扣费，验证段比较、对照 lifecycle 文档的验收红线。见 [`README.md`](friction_test/README.md)。 |
| [`REGIME_FRAMEWORK_GUIDE.md`](REGIME_FRAMEWORK_GUIDE.md) | 阶段一理论指导 | 市场状态分类的方法论文档，不是代码目录：TradFi 四大维度到 Crypto 的映射、加密永续特有维度、Python 落地方式。 |
| [`REGIME_ALPHA_EVALUATION_WORKFLOW.md`](REGIME_ALPHA_EVALUATION_WORKFLOW.md) | 阶段一理论指导 | 因子体检工作流 SOP：为什么不能物理切片数据、Point-in-time 条件掩码打标规范、决策分类矩阵。 |

风险与风格中性化原本是独立的"关卡2"，经讨论确认必须前移并入阶段一（详见
`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2 的顺序结论），已经落地在 `sherpa.risk`
（`exposure.rolling_beta`/`neutralize.neutralize`）+ `sherpa.backtest.style_exposure`，
并接入了上面 `alpha_research/`、`factor_orthogonalization/` 的各个脚本——不是 `research/`
下的独立子目录，而是内嵌进阶段一各产线的一个处理步骤。关卡2（基于 Regime 的动态多因子合成）已经开了
`factor_synthesis/` 目录，关卡3（换手摩擦与组合构建）在
`friction_test/`。

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

这四类之间刻意不共享中间结果文件（各自的 `README.md` 里都写了具体原因）：明细 CSV 只在各自内部闭环，
阶段之间唯一的传递物是研究线目录里的标准交接文件（`_shared/handoff.py`）——生产者负责按标准格式输出，
一个阶段改了自己的明细输出格式，不会连锁弄坏另一个阶段。
