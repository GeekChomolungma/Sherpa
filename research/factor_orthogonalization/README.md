# Factor Orthogonalization — 四大工程关卡 · 关卡1

对应 [`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`](../../QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md) §4
「关卡1：因子相关性分析与正交化 (Orthogonalization)」。

阶段一体检（`research/regime_factor_report/`、`research/alpha_research/worldquant_101/`）只回答"单个因子
有没有信息"；这里回答下一个问题——**如果同时选中好几个因子，它们之间是不是在重复下注同一
份信息**。如果 8 个因子两两相关系数 0.85~0.95，同时持有它们不会增加分散度，只会成倍放大同
一个方向的尾部风险。

## 这个模块要解决什么

0. **先中性化残差化，再做后面几步**（`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2）：每个候选
   因子的原始分数先套可流通性掩码，再用 `sherpa.risk.neutralize.neutralize()` 逐期截面 OLS
   剔除对 Beta（滚动对 `REGIME_BENCHMARK_SYMBOL`）、Size（`log(quote_volume)`）的被动暴露，
   只留残差。原因见下方"为什么先中性化，再做相关性聚类"。
1. 按 `config.REGIME_ALPHA_SETS` 手动指定的"12 个 regime 状态各自的候选因子集"，**在每个
   state 自己的历史切片内**逐对计算候选因子（残差分数）之间的**截面 Spearman 相关**（不是
   时序相关——见下方"为什么用截面相关"）。
2. 每个 (dimension, state) 切片各自按相关强度做单链聚类（single-linkage clustering），把
   高度相关的因子分进同一簇。
3. 每簇里只保留该 state 切片内信噪比（`|IC_IR|`）最高的一个"代表因子"，其余标记为冗余、
   建议剔除。

产出的是**建议**，不是自动执行的过滤器——最终要不要剔除某个因子，仍然需要研究者结合
`01_regime_factor_correlation_pairs.csv` 里的具体数字和自己对因子经济逻辑的理解来判断。

## 为什么要按 regime state 切片，而不是算一次全历史相关性了事

关卡3（基于微观 Regime 的动态多因子合成）最终是"regime 命中 state X 时，从 X 专属的因子
集合里挑权重"，所以两个因子是否冗余，必须在它们**真正会被放进同一个 state** 的那段历史上
检验——全历史看起来不太相关的一对因子，完全可能在具体某个 state 里其实高度重合，全局分析
会漏掉这种情况；反过来，全历史看起来相关的一对因子，也可能只是在某个占比很大的 state（比如
`liquidity=normal` 经常是采样最多的常态）里相关，在其它 state 里其实互补。

这一点已经用合成数据验证过：构造两个因子，让它们只在"BTC 进入强趋势"的那一段历史里高度
相关（截面相关 ~0.998），其它时段基本独立（~0.05~0.55）——全历史不做切片直接算，相关系数
只有 ~0.50，落在默认阈值 0.7 以下，会被误判成"不冗余"；而按 `trend=bull` 切片后能正确抓
到这对因子在这个 state 下的强冗余。

## 跟其它 research 子项目的关系：故意解耦，但不跟 sherpa 核心模块解耦

- **候选池不自动继承体检结果**。`config.py` 里的 `REGIME_ALPHA_SETS` 是手写的 qualified_name
  清单（默认值取自 `regime_factor_report/results/04_regime_matrix.csv` 的 Top3，只是作为
  示例抄了一份数字，运行时不读那份 CSV），不读取 `regime_factor_report/results/*.csv`、也
  不读取 `alpha_research/worldquant_101/regime_alpha_profile.csv`。想测哪些因子，自己往清单里加/删。
- **数据接入自成一份**（`data.py`），跟 `alpha_research/worldquant_101/data.py` 内容相似但完全独立维护，
  改这边的取数区间/频率不会影响那边，反之亦然。
- **regime 打标复用核心模块，不是解耦对象**。这里说的"解耦"针对的是其它 research 子项目
  的 CSV 中间产出（文件格式/目录结构可能随时变），不针对 `sherpa` 包本身——regime 归类直接
  调用 `sherpa.backtest.regime_screening.regime_report()`，这正是
  `alpha_research/worldquant_101/run_alpha_regime_profile.py` 产出 `04_regime_matrix.csv` 时用的同一个
  函数。这样才能保证这里聚类用的 state 跟 `04_regime_matrix.csv` 里说的是同一件事，不是
  自己另发明一套 regime 定义。
- 好处：候选池可以任意混搭——体检阶段表现好的世坤101因子、以后接入的 TradingView 因子、
  还没跑过完整体检的自定义因子，都能放在一起分析,不受某个体检脚本的文件格式或目录结构约束。

## 目录结构

```text
factor_orthogonalization/
├── config.py                  12 个 regime 状态各自的候选因子集 + 聚类阈值（手动维护）
├── data.py                    ClickHouse 取数入口（自成一份，不依赖其它 research 子项目）
├── clustering.py               并查集实现的单链聚类，纯函数、不碰 pandas/IO
├── run_orthogonalization.py   主脚本：取数 -> regime 打标 -> 算相关 -> 按 state 聚类 -> 落盘
├── README.md
└── results/
    ├── 01_regime_factor_correlation_pairs.csv   每一对因子在每个 state 一行的长表（主要阅读入口）
    └── 02_regime_cluster_assignments.csv        每个因子在每个 state 一行：所属簇 + keep/drop 建议
```

## 运行方法

```bash
CH_HOST=... CH_PASSWORD=... python research/factor_orthogonalization/run_orthogonalization.py
```

先在 `config.py` 里编辑：

- `REGIME_ALPHA_SETS`：12 个 regime 状态（`trend.bull/bear/neutral`、
  `volatility.high/normal/low`、`dispersion.high/normal/low`、
  `liquidity.high/normal/starved`）各自要测试哪些因子；
- `UNCONDITIONAL_ALPHAS`（可选）：要不要额外跑一组不区分 regime 的全历史对照；
- `CORRELATION_THRESHOLD`：多高的相关性算冗余。

## 为什么用「截面相关」而不是「IC 时序相关」

衡量"两个因子是不是在提供同一份信息"，工业界通常有两种角度：

1. **截面相关（本模块采用）**：在每一个时间截面 t，比较因子 A 给全市场 symbol 打的分数
   排序，和因子 B 给出的排序有多像。如果两个因子在每一期都把同一批币排在前面、同一批排
   在后面，那么无论它们各自的 IC 表现如何，选出来的持仓几乎是同一个组合——这才是"冗余"
   的准确定义，也是 Barra 式风格因子相关性分析的标准做法。
2. **IC 时序相关**：比较两个因子逐期 IC 值的时间序列走势像不像。这回答的是另一个问题
   ——"两个因子好/坏的时期是否同步"，跟"持仓是否重复"不是一回事：两个因子完全可能在同一
   时期都表现好，但选出来的具体持仓完全不同（互补而非冗余）。

所以这里用第 1 种，跟因子经济方向无关——`corr_mean` 强烈为负和强烈为正一样代表冗余（只是
簇里挑代表因子时不需要关心符号，因为持仓可以直接翻转方向）。判定聚类阈值时用的是
`abs(corr_mean)`，这一点在 `clustering.py`/`run_orthogonalization.py` 里都有体现。

## 实现上复用了什么

- **`sherpa.backtest.style_exposure.default_style_exposures` + `sherpa.risk.neutralize.neutralize`**：
  Beta/Size 暴露矩阵构造 + 逐期截面 OLS 残差化，见上方"这个模块要解决什么"第 0 步。
- **`sherpa.backtest.regime_screening.regime_report`**：产出跟 `04_regime_matrix.csv` 同一
  套 trend/volatility/dispersion/liquidity 四维度状态打标，逐 bar 对齐。
- **`sherpa.metrics.factor.rank_ic`**：本身只是"逐期对两个 (T,N) 矩阵做截面 Spearman
  corrwith"，标准用法是喂 `(alpha, forward_returns)` 算 IC，这里换成喂 `(alpha_a, alpha_b)`
  就直接得到两个因子的逐期截面相关序列，只对全历史算一次。
- **`sherpa.metrics.factor.conditional_ic_summary`**：把上面那条"因子间相关序列"或者"因子
  自身 ic_series"当成输入，按 `regime[dimension]` 分组，一次性拿到该维度下每个 state（含
  `ALL` 基线）各自的均值/标准差/samples——12 个 state 的切片统计不需要对每个 state 重新
  跑一遍 `rank_ic`，只是分组取行。
- **`sherpa.metrics.tradability.tradable_mask`**：跟 `alpha_research/worldquant_101/run_alpha_regime_profile.py`
  一致，算任何 IC/相关性之前先把"上线了但没有真实流动性"的 symbol 掩掉，避免插针小币
  污染秩相关。
- **`sherpa.alpha.base.registry`**：候选因子按 qualified_name（`"{family}.{name}"`）从全局
  registry 里取，天然兼容 worldquant / tradingview / custom 三大家族，新家族/自定义模块
  通过 `config.EXTRA_IMPORTS` 接入（见 `config.py` 顶部注释）。

## 结果文件怎么读

### `01_regime_factor_correlation_pairs.csv`（主要阅读入口）

一行 = 一对因子在一个 (dimension, state) 切片下的相关性统计，按
`dimension, state, abs_corr_mean` 排序：

| 列 | 含义 |
|---|---|
| `dimension` / `state` | 这一行属于哪个 regime 维度的哪个状态；`unconditional` / `ALL` 表示不区分 regime 的全历史对照（只有 `config.UNCONDITIONAL_ALPHAS` 非空时才会出现） |
| `alpha_a` / `alpha_b` | 这一对因子的 qualified_name |
| `samples` | 两个因子在**这个 state 切片内**都有有效分数的截面期数 |
| `corr_mean` | 该切片内逐期截面 Spearman 相关的均值（带符号） |
| `corr_std` | 上面那个序列在该切片内的标准差——越大说明这对因子的相关性本身越不稳定，解读 `corr_mean` 时要留意 |
| `abs_corr_mean` | `\|corr_mean\|`，排序 & 聚类判定都用这一列 |
| `high_correlation` | `abs_corr_mean >= config.CORRELATION_THRESHOLD` |
| `low_sample` | 该切片 `samples < 100` 或 `< 该维度 ALL samples 的 10%`——极端 state（比如样本天然很少的 `trend.bull`）算出来的强相关，可信度要打折扣，不能跟大样本 state 的结果同等看待 |

### `02_regime_cluster_assignments.csv`（最终建议）

一行 = 一个候选因子在一个 (dimension, state) 切片下的归属结果：

| 列 | 含义 |
|---|---|
| `dimension` / `state` | 同上 |
| `cluster_id` | 该切片内的簇编号（同一簇内两两之间至少存在一条 `high_correlation` 的传递路径，编号只在这个 (dimension, state) 范围内有意义，不能跨行比较） |
| `cluster_size` | 簇内因子数，`1` 表示这个因子在这个切片里跟候选集里其它因子都不冗余 |
| `cluster_members` | 簇内全部因子名 |
| `own_ic_mean` / `own_ic_std` / `own_ic_ir` | 该因子在**这个 state 切片内**相对未来收益的条件 IC 统计（`sherpa.metrics.factor.conditional_ic_summary` 的输出，跟阶段一体检同一套指标口径） |
| `own_samples` / `own_low_sample` | 该因子自身这个切片内的样本量与 low-sample 标记 |
| `is_representative` | 是否是簇内该切片 `\|own_ic_ir\|` 最高、被选中保留的代表因子 |
| `recommendation` | `keep` 或 `drop_redundant` |
| `redundant_with` | 若被建议剔除，指出它跟簇内哪个代表因子冗余 |

## 局限性 / 下一步

- 聚类用的是简单的单链聚类（阈值处截断的并查集），不是 `scipy.cluster.hierarchy` 那种完整
  的层次聚类树——候选池按设计是研究者手动圈定的小规模集合，简单实现足够用；见
  `clustering.py` 顶部注释。
- 12 个 state 是彼此独立分析的：同一个因子在 `trend.bull` 里被标记 `drop_redundant`，不代表
  它在 `trend.bear` 里也冗余，两行结果要分开看，不要跨 state 类比。
- 这里只做「关卡1」（去冗余）。风险与风格中性化已经前移并入阶段一体检（见
  `QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` §3.2），本模块内部也已经接了这一步（见上方第 0
  步），不再是独立关卡。基于 Regime 的动态合成（现为关卡2）、换手摩擦压力测试（现为关卡3）
  仍是各自独立的下一步，不在本模块范围内。
