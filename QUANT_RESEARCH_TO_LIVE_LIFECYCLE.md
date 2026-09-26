# 从单因子研究到实盘生产：量化策略全生命周期与模块归属准则

> 本文档为 Sherpa 量化系统的**顶层工程准则（Master Engineering Guideline）**，系统性规范从单因子挖掘、跨越三大工程关卡、构建投资组合，直至历史回测、纸面交易与实盘放量的完整全生命周期。
> 
> 本文档清晰定义了每一个生命周期阶段**在代码库中的模块归属**以及**对应的 Research 专题研究文档与实战工程索引**，作为后续量化研发与文档演进的统一总纲。
>
> **版本变更说明**：原"四大工程关卡"中的**关卡2（风险与风格中性化）**，经讨论确认必须**前移并入阶段一（单因子挖掘与体检）**——因子的截面残差化（剔除 Beta/Size 暴露）必须发生在因子相关性聚类（原关卡1）之前，否则聚类算出来的"相关性"会把"共同承担同一份被动风险暴露"误判成"信息冗余"，错误地淘汰掉本来互补的因子。因此本文档现行版本只保留**三大工程关卡**，编号相应前移（原关卡3→关卡2，原关卡4→关卡3）。

---

## 目录
1. [全生命周期总览图与架构划分](#1-全生命周期总览图与架构划分)
2. [全生命周期文档与工程索引全景表](#2-全生命周期文档与工程索引全景表)
3. [阶段一：单因子挖掘与体检 (Alpha Research)](#3-阶段一单因子挖掘与体检-alpha-research)
   - [3.1 职责边界与准入准出](#31-职责边界与准入准出)
   - [3.2 中性化：截面风险与风格暴露残差化 (Neutralization)](#32-中性化截面风险与风格暴露残差化-neutralization)
   - [3.3 对应 Research 文档与实操指南](#33-对应-research-文档与实操指南)
   - [3.4 对应代码模块归属](#34-对应代码模块归属)
4. [桥梁关卡：从残差因子到投资组合的三大核心门槛 (The 3 Gates)](#4-桥梁关卡从残差因子到投资组合的三大核心门槛-the-3-gates)
   - [关卡 1：因子相关性分析与正交化 (Orthogonalization)](#关卡-1因子相关性分析与正交化-orthogonalization)
   - [关卡 2：基于微观 Regime 的动态多因子合成 (Synthesis)](#关卡-2基于-微观-regime-的动态多因子合成-synthesis)
   - [关卡 3：第二层可变现性与资金容量压力测试 (Friction Test)](#关卡-3第二层可变现性与资金容量压力测试-friction-test)
   - [关卡对应指导文档与设计原理](#关卡对应指导文档与设计原理)
5. [阶段二：投资组合严格时序回测 (Portfolio Backtesting)](#5-阶段二投资组合严格时序回测-portfolio-backtesting)
   - [5.0 承上启下：研究阶段交出了什么，阶段二接手什么](#50-承上启下研究阶段交出了什么阶段二接手什么)
   - [5.1 职责边界与核心规范](#51-职责边界与核心规范)
   - [5.2 对应指导文档与示例工程](#52-对应指导文档与示例工程)
   - [5.3 对应代码模块归属](#53-对应代码模块归属)
6. [阶段三：生产环境纸面交易 (Paper Trading / Staging)](#6-阶段三生产环境纸面交易-paper-trading--staging)
   - [6.1 职责边界与验收指标](#61-职责边界与验收指标)
   - [6.2 对应指导文档与示例工程](#62-对应指导文档与示例工程)
   - [6.3 对应代码模块归属](#63-对应代码模块归属)
7. [阶段四：小资金实盘与阶梯放量 (Canary Live & Scaling)](#7-阶段四小资金实盘与阶梯放量-canary-live--scaling)
   - [7.1 职责边界与风控规范](#71-职责边界与风控规范)
   - [7.2 对应代码模块与外部系统边界](#72-对应代码模块与外部系统边界)
8. [Sherpa 底层代码模块调用关系矩阵](#8-sherpa-底层代码模块调用关系矩阵)

---

## 1. 全生命周期总览图与架构划分

在工业级量化体系中，**“单因子（Alpha）”绝不等于“策略（Strategy）”**。从数学信息到账户资金的稳健增长，必须跨越一条完整的生产流水线：

```mermaid
flowchart TD
    subgraph STAGE1["阶段一：单因子挖掘与体检 (Alpha Research)"]
        A1["算子计算: ops.py / worldquant / tradingview"]
        A2["中性化残差化: sherpa.risk.rolling_beta + neutralize (逐期截面OLS剔除Beta/Size暴露)"]
        A3["第一层检验: run_alpha_check (对残差分数算 RankIC, IC_IR, 单调性)"]
        A4["Regime 掩码画像: 残差分数的条件 IC_IR / 淘汰纯噪音"]
    end

    subgraph GATES["工业界核心桥梁：三大工程关卡 (The 3 Gates)"]
        direction TB
        G1["关卡 1: 相关性聚类与正交化 (对残差因子聚类，剔除影子因子)"]
        G2["关卡 2: 基于微观 Regime 动态合成组合 (TargetPosition)"]
        G3["关卡 3: 全摩擦换手与资金容量测试 (漂移扣费)"]
    end

    subgraph STAGE2["阶段二：投资组合严格回测 (Portfolio Backtesting)"]
        B1["HistoricalPanelSource 连续驱动 (防前视切片)"]
        B2["Simulator 事件驱动撮合 (多大时代牛熊压力测试)"]
        B3["绩效归因: Sharpe, Calmar, MaxDrawdown, TurnoverDecay"]
    end

    subgraph STAGE3["阶段三：生产纸面交易 (Paper Trading / Staging)"]
        P1["LivePanelSource 监听 Redis (kline_ready / 1m 200窗)"]
        P2["Runner + BaseStrategy 实时推流"]
        P3["LogSink 写入 LiveOrderRequest (验证 500ms 时延与幂等 key)"]
    end

    subgraph STAGE4["阶段四：小资金实盘与阶梯放量 (Canary Live & Scaling)"]
        L1["WebhookSink 派发信号至外部 Webhooker / OM"]
        L2["实盘撮合滑点基差监控与资金阶梯放量"]
    end

    STAGE1 --> GATES
    GATES --> STAGE2
    STAGE2 --> STAGE3
    STAGE3 --> STAGE4
```

---

## 2. 全生命周期文档与工程索引全景表

为了让读者清晰掌握当前代码库中各个文档所处的研究阶段与具体作用，下表给出了全局映射全景图：

| 生命周期阶段 | 核心任务目标 | 关联 Research 文档 / 系统指南 | 文档核心作用与解决的痛点 |
| :--- | :--- | :--- | :--- |
| **阶段一：单因子挖掘与体检<br>*(Alpha Research)*** | 因子数学表达、全时序计算、**截面中性化残差化（剔除 Beta/Size 被动暴露）**、无前视因果打标、环境适应性体检、指标数值量级标尺与品性诊断 | 📘 [`docs/ALPHA_METRIC_BENCHMARKS.md`](file:///d:/code-repo/Chomo/Sherpa/docs/ALPHA_METRIC_BENCHMARKS.md)<br><br>📘 [`research/REGIME_FRAMEWORK_GUIDE.md`](file:///d:/code-repo/Chomo/Sherpa/research/REGIME_FRAMEWORK_GUIDE.md)<br><br>📘 [`research/REGIME_ALPHA_EVALUATION_WORKFLOW.md`](file:///d:/code-repo/Chomo/Sherpa/research/REGIME_ALPHA_EVALUATION_WORKFLOW.md)<br><br>🛠️ [`research/alpha_research/worldquant_101/`](file:///d:/code-repo/Chomo/Sherpa/research/alpha_research/worldquant_101) | **体检指标体系与量级基准**：规范 `ic_mean`、`ic_std`、`ic_ir`、`win_rate`、`samples`、`ic_ir_gap` 的数学物理本质与工业级及格/优秀/神级量级标尺，给出多指标交叉诊断口诀。<br><br>**市场状态分类准则**：建立 TradFi 四大维度到 Crypto 的 1:1 映射，补充永续合约特有的资金费率与杠杆维度，给出 BTC 减半宏观情景切片与 Python 代码。<br><br>**工业级单因子测评 SOP**：阐述“全时序连续计算、严格 Point-in-time 条件掩码打标”机制，剖析物理切片四大暗礁，输出因子决策矩阵。<br><br>**首个落地研究项目**：基于真实 ClickHouse 全量 4h 数据，完成世坤 101 因子的批量筛选与排行榜产出。<br><br>**中性化落地**：`sherpa.risk`（`rolling_beta`/`neutralize`）已完成代码落地并有单测覆盖；`research/` 侧各体检脚本（尤其是 `alpha_research/worldquant_101/`、`factor_orthogonalization/`）改用残差分数的整合工作待后续任务同步。 |
| **三大桥梁关卡<br>*(Portfolio Construction)*** | 因子去冗余正交化、基于微观 Regime 动态组装组合大脑 | 📘 [`docs/backtest_principle.md`](file:///d:/code-repo/Chomo/Sherpa/docs/backtest_principle.md)<br><br>🔖 *(预留规划中文档)* | **回测两层第一性原理**：系统性阐明信息预测力（第一层）与资金可变现性（第二层）的鸿沟，推导因果律 Shift-1、去均值 L1 归一化与被动持仓漂移公式。<br><br>*(后续将补充: 因子正交化实操、Regime 路由动态加权指南)* |
| **阶段二：投资组合回测<br>*(Portfolio Backtesting)*** | 宏观多时代切片压力测试、事件驱动逐 Bar 撮合、综合净值与风控归因 | 📘 [`docs/backtest_principle.md`](file:///d:/code-repo/Chomo/Sherpa/docs/backtest_principle.md)<br><br>💻 [`examples/vectorized_research.py`](file:///d:/code-repo/Chomo/Sherpa/examples/vectorized_research.py)<br><br>💻 [`examples/runner_backtest_with_stop_loss.py`](file:///d:/code-repo/Chomo/Sherpa/examples/runner_backtest_with_stop_loss.py) | **回测第二层原理落地**：严格扣除摩擦、滑点与换手衰减。<br><br>**向量化回测范例**：极速验证组合逻辑。<br><br>**事件驱动回测范例**：基于 `Runner` + `Simulator` 运行跨 Bar 状态止损策略。 |
| **阶段三：生产纸面交易<br>*(Paper Trading)*** | 监听真实 Redis 1m 截面通知、验证 500ms 时延预算与幂等 key 稳定性 | 📘 [`sherpa/data/DATA_STRUCTURES_AND_TRANSFORMS.md`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/DATA_STRUCTURES_AND_TRANSFORMS.md)<br><br>💻 [`examples/paper_trading_log_sink.py`](file:///d:/code-repo/Chomo/Sherpa/examples/paper_trading_log_sink.py) | **数据契约与流式规范**：阐明长表转 `BarPanel`、1m `WindowCache` 滑窗与 `MarketEvent` 信封机制。<br><br>**纸面交易标准示范**：运行 `LivePanelSource`，通过 `LogSink` 实时打印标准化的 `LiveOrderRequest`。 |
| **阶段四：小资金实盘<br>*(Live Execution)*** | 派发信号至外部 Webhooker、监控真实撮合滑点、阶梯扩充资金容量 | 📘 [`docs/SHERPA_DESIGN.md`](file:///d:/code-repo/Chomo/Sherpa/docs/SHERPA_DESIGN.md)<br><br>🔖 *(预留规划中文档)* | **架构边界定义**：Sherpa 止步于 `WebhookSink` 生成标准化信号意图，明确下游 Webhooker 撮合与 PMS 资金清算边界。<br><br>*(后续将补充: 实盘滑点基差监控与订单执行算法 SOP)* |

---

## 3. 阶段一：单因子挖掘与体检 (Alpha Research)

### 3.1 职责边界与准入准出
* **职责边界**：纯数学与统计信息层面的假说检验。评估单个因子在微观层面是否具有超额预测力，并出具其在不同市场气候下的环境适应性体检表。**本阶段严禁构建实际交易持仓，严禁在此阶段计算夏普比率或 PnL**。本阶段现在包含完整的"原始分数 → 截面中性化残差 → Regime 条件体检"链路（见 §3.2），不再只是对原始因子分数直接体检。
* **准入**：全量连续的 [`BarPanel`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/schema.py#L57-L138) 数据（通常为 3~5 年完整历史）。
* **准出标准**：
  * 淘汰全局无条件 $\text{IC\_IR} < 0.10$ 的纯噪音因子；
  * 淘汰"中性化后信息量大幅衰减/消失"的因子——如果一个因子的原始 $\text{IC\_IR}$ 表现优异，但剥离 Beta/Size 暴露后的残差 $\text{IC\_IR}$ 显著下降甚至转为噪音，说明其原始表现本质上是被动承担系统性风险（俗称"骑 Beta"），而不是真正的选币能力，必须淘汰，不得带着未剥离的原始分数进入关卡1；
  * 输出每个因子（残差化后）在各微观 Regime 掩码下的条件体检矩阵（识别出哪些是全天候因子、哪些是需条件激活动态门控因子）；
  * **显著性判别（统计门槛）**：见下方「显著性检验与选因子规则」。

#### 显著性检验与选因子规则

* **为什么需要**：IC_IR 只衡量"信号强度"，不考虑样本量。同样 IC_IR = 0.3，在 1 万根 bar 上是铁证，在某个只有 50 根 bar 的 regime 切片里可能只是运气。显著性检验把"强度"和"样本量"合成一个判断：这个 IC 均值有多大把握不是 0。
* **检验方法**：对残差 IC 序列（全局，以及每个 regime 切片）的均值做 **Newey–West t 检验**（[`sherpa.metrics.factor.ic_significance`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/factor.py)），输出 `t_stat` 与双侧 `p_value`：
  * 朴素做法 `t = IC_IR × √n` 假设各期 IC 相互独立；但因子值逐 bar 变化慢，相邻 IC 往往正相关，朴素 t 会**系统性高估**显著性；
  * Newey–West 把前 L 阶自协方差加进方差估计（L = ⌊4·(n/100)^(2/9)⌋，全样本约 11 阶），自相关越强、t 越小。
* **门槛：|t| ≥ 3.0**（双侧 p ≈ 0.0027）。理由是多重检验：约 100 个因子 × 12 个 regime state ≈ 1200 次检验，|t| ≥ 3 时纯靠运气"显著"的期望个数约 3 个，而传统的 |t| ≥ 2 会有约 55 个。Harvey, Liu & Zhu (2016) 也主张新因子的 t 值门槛提高到 3.0。
* **选因子规则（`04_regime_matrix.csv` → 关卡1 候选池）**：
  1. **门槛**：每个 regime state 内，只有条件 IC 均值 |t| ≥ 3 的因子才有资格入选；
  2. **排序**：通过门槛的因子按 |IC_IR| 从高到低取 Top K（默认 5）；
  3. **不凑数**：通过门槛的不足 K 个，就只取通过的，不拿不显著的因子补位；`04_regime_matrix.csv` 的 `significant_count` 列记录每个 state 实际通过了几个。
* **为什么是"显著性做门槛、|IC_IR| 做排序"，而不是按 t 值或 p 值排序**：同一个 state 里各因子的样本数几乎相同，t ≈ IC_IR × √n_eff，按 t 排序和按 IC_IR 排序基本等价，剩下的差别只来自 IC 自相关的差异，并不代表因子更强；而 p 值衡量的是"有多确定不是 0"，不是"效应有多大"，样本一大，微弱的效应也能拿到极小的 p 值。显著性回答"能不能用"，|IC_IR| 回答"有多强"，各管一件事。
* **落地位置**：`t_stat`/`p_value` 由 `conditional_ic_summary` 随条件 IC 一起算出，写进 `regime_alpha_profile.csv`；门槛在 [`research/regime_factor_report/regime_factor_report.py`](file:///d:/code-repo/Chomo/Sherpa/research/regime_factor_report/regime_factor_report.py) 的 `build_regime_matrix` 执行（参数 `--min-abs-t`，`run_research.sh` 里的环境变量 `MIN_ABS_T`，默认 3.0）；`run_screening.py` 的全局排行榜也附带这两列，仅作参考，不改变其 `passed` 口径。
* **局限**：|t| ≥ 3 只是对多重检验的粗粒度防护，不是严格校正；将来自动挖掘因子、检验次数上到成千上万时，需要配合候选记账与 Deflated Sharpe 等更严格的方法（见 [`research/factor_orthogonalization/INCREMENTAL_TODO.md`](research/factor_orthogonalization/INCREMENTAL_TODO.md) G7）。

### 3.2 中性化：截面风险与风格暴露残差化 (Neutralization)

* **核心痛点**：许多虚假的“神级因子”本质上只是被动承担了系统性风险（如持续做多高 Beta 山寨币、做空低 Beta 稳健币）。这种因子的高 IC_IR 是"追随 Beta 换了个马甲"，一旦大盘转熊、或者 Regime 判定出现滞后/误判，策略将遭受断崖式亏损；更隐蔽的是，多个这样的因子彼此之间会呈现出很高的相关性——但那只是因为它们共享了同一份被动风险暴露，不是因为它们在表达同一份选股信息。
* **为什么必须放在阶段一、且在关卡1（正交化）之前**：关卡1的相关性聚类衡量的应该是"两个因子是否提供重复信息"。如果先聚类、后中性化，聚类算出来的高相关性可能只是两个因子共同承担了同一份 Beta 暴露的假象，会错误地把本来互补、只是共享了风险底色的因子当成冗余因子剔除掉。只有先把每个候选因子残差化，再拿残差分数去做相关性聚类和 Regime 条件体检，才能保证聚类测的是"残差信息层面"的真实重复度。
* **处理规范**：
  1. **构建风险暴露矩阵**：Beta 暴露用 [`sherpa.risk.exposure.rolling_beta`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk/exposure.py) 计算每个 symbol 对 `BTCUSDT` 的滚动 beta（**逐 symbol 逐时刻都不同的 `(T,N)` 矩阵**，不能直接用 BTC 自身的涨跌幅——那是同一截面内对所有 symbol 恒定的标量，没有横截面方差，无法作为回归自变量）；Size 暴露直接复用 `panel.quote_volume`（或其 `ops.log`/`ops.rank` 变换）。
  2. **逐期截面 OLS 回归取残差**：用 [`sherpa.risk.neutralize.neutralize`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk/neutralize.py) 对每个候选因子的原始分数矩阵，**逐个时间戳独立**做一次截面多重回归（`raw_score(t) ~ 截距 + beta(t) + size(t)`），取残差拼回一张 `(T,N)` 矩阵。逐期独立回归而不是把整个历史 pool 成一次全局 OLS，是因为因子对 Beta/Size 的敏感度不假设是跨越牛熊震荡的常数——这一点跟 Barra 风险模型的标准做法一致。
  3. **残差矩阵替换原始分数**：后续 §3.1 的第一层统计检验（`run_alpha_check`）、Regime 条件 IC 画像、以及关卡1 的相关性聚类，全部改用这张残差矩阵，不再使用 `alpha.compute(panel)` 的原始输出。
* **对应 Sherpa 模块归属**：[`sherpa.risk`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk)（`exposure.rolling_beta`、`neutralize.neutralize`）。跟 `sherpa.metrics`/`sherpa.portfolio` 同一条包级约定：只依赖 pandas/numpy，不 import 仓库内其他模块，可脱离 Sherpa 其余部分单独复用/测试；`BarPanel` 拆包这一步交给调用方（未来的 `sherpa.backtest` 适配层或 research 脚本）。

### 3.3 对应 Research 文档与实操指南
读者在进行本阶段研发时，应严格遵循以下四篇核心文档：
1. **体检指标体系与经验基准**：[`docs/ALPHA_METRIC_BENCHMARKS.md`](file:///d:/code-repo/Chomo/Sherpa/docs/ALPHA_METRIC_BENCHMARKS.md)
   * **作用**：因子体检的“度量衡手册”。详述 `ic_mean`、`ic_std`、`ic_ir`、`win_rate`、`samples`、`baseline_ic_ir`、`ic_ir_gap` 的数学与物理本质，给出美股日频与加密 4h 的及格/优质/神级经验数值区间，并提供多指标交叉诊断决策树与实操避坑口诀。
2. **理论底座**：[`research/REGIME_FRAMEWORK_GUIDE.md`](file:///d:/code-repo/Chomo/Sherpa/research/REGIME_FRAMEWORK_GUIDE.md)
   * **作用**：指导读者如何用科学客观的指标对市场状态进行分类。详细给出了传统金融四大维度（趋势、波动率、离散度、流动性）到加密资产的 1:1 观测指标映射，追加了加密永续合约专属的“资金费率与杠杆率”维度，并提供了在 Sherpa 中开箱即用的 Python 计算函数。
3. **测评工作流 SOP**：[`research/REGIME_ALPHA_EVALUATION_WORKFLOW.md`](file:///d:/code-repo/Chomo/Sherpa/research/REGIME_ALPHA_EVALUATION_WORKFLOW.md)
   * **作用**：指导读者如何科学执行测评。阐明为什么绝不能物理切断数据（分析了冷启动缺失、后视镜前视泄露、状态切换盲区、小样本拟合四大暗礁），确立了“全时序连续计算 + 严格 Point-in-time 条件掩码打标”的工业级规范，并给出了决策分类矩阵。
4. **实战工程项目**：[`research/alpha_research/worldquant_101/`](file:///d:/code-repo/Chomo/Sherpa/research/alpha_research/worldquant_101)
   * **作用**：世坤 101 因子库在真实 ClickHouse 4h 数据上的筛选实战。包含取数脚本 `data.py`、批量筛选脚本 `run_screening.py` 以及各分类因子的执行模块。**待更新**：目前仍对原始分数体检，接入 §3.2 中性化残差化是下一步待同步的整合工作。

### 3.4 对应代码模块归属
* **算子与因子表达**：[`sherpa.alpha`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/base.py)（`Alpha`、`ops.py`、`worldquant/`、`tradingview/`、`custom/`）。
* **特征组织容器**：[`sherpa.alpha.engine.AlphaEngine`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/engine.py#L14-L41)（管理因子集合，输出特征矩阵）。
* **风险暴露与中性化残差化**：[`sherpa.risk`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk)（`exposure.rolling_beta`、`neutralize.neutralize`，见 §3.2）。
* **统计评测库**：[`sherpa.metrics.factor`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/factor.py)（`rank_ic`、`ic_summary`、`ic_significance`（Newey–West t 检验）、`conditional_ic_summary`、`quantile_returns`、`is_monotonic_decreasing`）。

---

## 4. 桥梁关卡：从残差因子到投资组合的三大核心门槛 (The 3 Gates)

因子通过了阶段一的体检（此时已经是剥离过 Beta/Size 暴露的残差 Alpha）后，**绝不能直接作为独立策略实盘**。必须经过以下三个严苛关卡，将其组装成抗周期的投资组合：

### 关卡 1：因子相关性分析与正交化 (Orthogonalization)
* **核心痛点**：若选出 8 个在趋势市表现优秀的动量因子，其相关系数可能高达 $0.85 \sim 0.95$。同时押注它们不仅没有增量信息，反而会成倍放大特定方向的尾部风险。
* **处理规范**：
  1. 计算候选因子（**阶段一中性化残差化之后**的分数，不是原始分数——见 §3.2）之间的 Spearman 秩相关矩阵；
  2. 进行层次聚类（Hierarchical Clustering）或施密特正交化（Gram-Schmidt）；
  3. 每个高度相关的簇（Cluster）中，**仅保留信噪比最高或逻辑最简洁的一个因子**，确保进入组合的因子相互正交、彼此互补。
* **对应 Sherpa 模块归属**：`research/` 专项聚类脚本 + [`sherpa.metrics.factor`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/factor.py)。
* **实操与后续规划**：[`research/factor_orthogonalization/`](research/factor_orthogonalization)（现有实现）；新因子增量检验的规划见 [`INCREMENTAL_TODO.md`](research/factor_orthogonalization/INCREMENTAL_TODO.md)。

### 关卡 2：基于微观 Regime 的动态多因子合成 (Synthesis)
* **核心痛点**：因子在不同宏观/微观环境下各有利弊。如何让策略在正确的时机调用正确的因子？
* **处理规范**：
  1. **构建组合大脑**：在策略层的 [`on_bar`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/base.py#L27-L29) 中，读取当期 Point-in-time 的 Regime 状态标签；
  2. **动态路由与权重分配**：
     * 强趋势/高离散时，提高动量与突破因子的权重分配；
     * 窄幅震荡/低波时，切换至成交量均值回归因子；
  3. **平滑过渡约束**：引入权重变化缓冲（Hysteresis Buffer），严禁在相邻两期进行“非 0 即 100%”的极端剧烈翻转。
* **执行文档（设计阶段）**：[`research/factor_synthesis/README.md`](research/factor_synthesis/README.md)（基线 → Regime 路由 → 平滑的方案阶梯、walk-forward 验证、holdout 规矩）。
* **对应 Sherpa 模块归属**：[`sherpa.strategy.base.BaseStrategy`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/base.py#L16-L30)（编写业务组合逻辑）+ [`sherpa.portfolio.weighting`](file:///d:/code-repo/Chomo/Sherpa/sherpa/portfolio/weighting.py)（`demean_l1` 截面资金中性、`top_k_long_short` 等，把合成后的 alpha 分数映射成目标持仓权重）。

### 关卡 3：第二层可变现性与资金容量压力测试 (Friction Test)
* **核心痛点**：第一层理论收益极高的多因子组合，往往因为极高的换手率，在真实扣除手续费和滑点后净值完全磨平。
* **处理规范**：
  1. **被动持仓漂移追踪**：准确计算持有期内因各资产涨跌导致的权重偏移 $W^{\text{drift}}$，得出真实物理换手率；
  2. **摩擦压力测试**：分别注入 `ZeroCostModel`（测毛利）与 `FixedFeeCostModel(fee_bps=5, slippage_bps=3)`（测净利）；
  3. **指标验收红线**：扣费后净 Sharpe $\ge 2.5$，换手衰减率（Turnover Decay）$< 40\%$。
* **对应 Sherpa 模块归属**：[`sherpa.backtest.cost_model`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/cost_model.py) + [`sherpa.portfolio.turnover`](file:///d:/code-repo/Chomo/Sherpa/sherpa/portfolio/turnover.py)（`drift_weights`、`turnover`）。

### 关卡对应指导文档与设计原理
* **核心指导文档**：[`docs/backtest_principle.md`](file:///d:/code-repo/Chomo/Sherpa/docs/backtest_principle.md)
  * **作用**：详细推导了从“数学预测力”跨越到“资金约束与物理摩擦”的第一性原理，规范了因果律时钟对齐、截面去均值 + L1 归一化公式、真实换手率定义与换手衰减率计算法则。
* *(注：后续关卡成熟后，将在 `research/` 目录下追加《多因子正交化实战指南》与《Regime 组合路由优化指南》)*。

---

## 5. 阶段二：投资组合严格时序回测 (Portfolio Backtesting)

### 5.0 承上启下：研究阶段交出了什么，阶段二接手什么

> 这一节是全局视角的"定位锚"：在阶段一和三大关卡里钻得很深之后，回到这里确认自己在整条链路的哪一段、在回答什么问题。

**截面量化的本质**：每一期给全部可交易标的打一个分数，用**分数的排序**去预测**未来收益的相对排序**，再把排序变成多空仓位——做多分数靠前的、做空分数靠后的，赚的是强弱之间的差，而不是赌大盘涨跌。

**阶段一 + 三大关卡在做什么：找到排序能力强、且能落地成仓位的 alpha 配方。**

| 环节 | 回答的问题 | 主要优化的量 |
|---|---|---|
| 阶段一 单因子体检 | 单个因子（剥离 Beta/Size 后）的排序能力是否真实、显著、在哪些 regime 下成立？ | IC / IC_IR / 显著性 |
| 关卡1 去冗余 | 选出来的因子是不是在重复下注同一份信息？ | 因子之间的独立性 |
| 关卡2 合成 | 多个因子怎么合成一个分数，样本外排序能力最强？ | 合成分数的 IC |
| 关卡3 摩擦与容量 | 分数变成仓位、扣掉手续费 / 滑点 / 资金费率之后还剩多少？组合怎么构建最划算？ | 净收益、换手、容量 |

可以用主动管理基本定律把这四步串起来看：

```text
信息比率 IR ≈ IC × √广度 × TC − 成本拖累
              └阶段一~关卡2┘        └──── 关卡3 ────┘
```

- **IC**：排序预测得准不准，阶段一到关卡2 主要在提高它；
- **广度**：每年独立下注的次数，由币池大小和调仓频率决定；
- **TC（传导系数）**：分数变成仓位时保留了多少预测力，取决于组合构建方式（Top-K 等权还是按分数配权、仓位上限、Beta 对冲……）；
- **成本拖累**：手续费、滑点，以及永续合约特有的资金费率。

IC 再高，换手过大、成本过重，净收益也会被吃光——所以关卡3 和前面的环节同样重要。

**阶段一和三大关卡的最终产物：一份冻结的"alpha 配方"**，而不只是"几个因子 + 一组权重"。实盘要算出和回测一模一样的分数，下面每一项都必须原样复现：

| 配方组成 | 内容 | 来自 |
|---|---|---|
| 可交易池 | 流动性掩码规则（每期剔除没有真实成交的标的） | 阶段一 |
| 因子定义 | 因子公式与窗口参数（qualified_name 即可定位） | 阶段一 |
| 中性化 | 每期对 Beta / Size 做截面回归取残差——研究用的全是**残差分数**，实盘漏掉这一步就是另一个信号 | 阶段一 §3.2 |
| IC 标签口径 | 持有期、执行延迟（`research/research_config.json` 的 `label`），决定了配方"假设在什么时点成交" | 阶段一 |
| 因子集合 | 每个 regime state 下保留的因子（`factor_synthesis/config.py`） | 关卡1 |
| 合成规则 | 截面标准化、方向、权重（可能随 regime state 变化）、平滑 / 迟滞、权重的定期重估规则 | 关卡2 |
| regime 打标 | 实时算出当前 state 的规则——权重随 state 变，state 本身就是配方的一部分 | 阶段一 / 关卡2 |
| 组合构建规则 | 分数 → 仓位的映射（Top-K / 按分数配权）、K 的取值、调仓频率、换手缓冲带、仓位上限、Beta 对冲 | 关卡3 |
| 成本假设 | 手续费、滑点、资金费率的建模口径 | 关卡3 |

**阶段二的输入：就是上面这份冻结的配方。** 阶段二不再"找因子"、不再"调权重"，只回答一个问题：

> 把配方原封不动地放进逐 bar 推进的真实时序里（严格因果、扣除全部摩擦、历经多个牛熊周期），它还赚不赚钱？

因此：

- **阶段二是验证，不是搜索。** 回测结果不好，要回到对应的关卡去改配方，改完再整体重新验证；在回测里反复改参数看夏普，就是在对回测过拟合；
- **样本外 holdout 在这里用掉**：配方冻结后，在 `research_end ~ holdout_end` 上跑一次，结果如实记录，不回头调参（`research/factor_synthesis/README.md` §6.4）；
- **阶段三、四吃的还是同一份配方**：阶段三验证实盘链路算出的分数与回测逐笔一致（工程一致性，不是再验证一次 alpha）；阶段四验证真实成交的滑点、资金费与回测假设一致，再阶梯放量；
- **整条链路是一个循环，不是直线**：上线后持续监控每个因子的滚动 IC，因子会衰减、会被拥挤交易掉；权重按计划重估，衰减的因子降权 / 下线，新因子从挖掘入口进来，再走一遍阶段一和三大关卡。

### 5.1 职责边界与核心规范
* **职责边界**：将三大关卡打磨完成的组合策略注入真实的因果律时序驱动器中，考核其跨越多年历史、历经多种宏观牛熊周期（BTC 减半前中后期）下的整体净值曲线、回撤深度与风控表现。
* **核心规范**：
  * **因果律物理防线**：使用 [`HistoricalPanelSource`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L32-L87)，逐 Bar 截取 $\le t$ 的数据窗口；
  * **撮合因果律对齐**：通过 [`Simulator`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/event_driven.py#L34-L100) 确保 $t$ 时刻根据闭合 K 线计算的意图，严格在 $t+1$ 周期开始生效，并在收益实现时扣减调仓换手成本；
  * **多大时代压力测试（Scenario Testing）**：必须在宏观情景切片（如深熊底部、ETF暴拉主升、减半后大洗盘）下分别输出独立的风控报表。

### 5.2 对应指导文档与示例工程
1. **理论原理**：[`docs/backtest_principle.md`](file:///d:/code-repo/Chomo/Sherpa/docs/backtest_principle.md)（第 2 节·真实可变现性验证）。
2. **向量化极速回测范例**：[`examples/vectorized_research.py`](file:///d:/code-repo/Chomo/Sherpa/examples/vectorized_research.py)
   * 演示如何对截面权重进行整体 `shift(1)` 并考虑 `drift_weights` 快速生成净值曲线。
3. **事件驱动带状态回测范例**：[`examples/runner_backtest_with_stop_loss.py`](file:///d:/code-repo/Chomo/Sherpa/examples/runner_backtest_with_stop_loss.py)
   * 演示如何在 `BaseStrategy` 中维护跨 Bar 浮亏状态，并由 `Simulator` 撮合执行无条件止损策略。

### 5.3 对应代码模块归属
* **数据驱动**：[`sherpa.data.panel_source.HistoricalPanelSource`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L32-L87) + [`sherpa.data.universe.Universe`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/universe.py)。
* **回测撮合引擎**：[`sherpa.backtest.event_driven.Simulator`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/event_driven.py#L34-L100) / [`sherpa.backtest.vectorized`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/vectorized.py)。
* **调度外壳**：[`sherpa.strategy.runner.Runner.run_backtest`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/runner.py#L39-L42) + [`sherpa.strategy.sink.BacktestSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/backtest_sink.py#L15-L21)。
* **绩效指标**：[`sherpa.metrics.performance`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/performance.py)（Sharpe, Calmar, MaxDrawdown, TurnoverDecay）。

---

## 6. 阶段三：生产环境纸面交易 (Paper Trading / Staging)

### 6.1 职责边界与验收指标
* **职责边界**：**不涉及真金白银下单，但在真实生产环境完全模拟实盘运行（持续至少 2~4 周）**。重点排查代码工程缺陷、网络时延、计算性能瓶颈与信号一致性。
* **核心验收指标**：
  1. **计算时延预算（Latency Budget）**：每分钟截面事件到达后，全市场所有 Alpha 特征计算 + 策略打分必须在 **500 毫秒** 内完成并生成意图；
  2. **信号确定性与幂等性**：验证生成的 [`LiveOrderRequest`](file:///d:/code-repo/Chomo/Sherpa/sherpa/live/request.py#L33-L44) 具有稳定的 `idempotency_key`（`f"{strategy_id}:{bar_end_time}:{symbol}"`），在网络重试或重放时不发生重复发单；
  3. **离线/在线信号对齐（Offline-Online Parity）**：取一段纸面交易期间的日志，与离线回测产生的信号逐笔比对，相关系数必须等于 $1.000$（无环境差错或隐藏 bug）。

### 6.2 对应指导文档与示例工程
1. **数据底层与信封契约**：[`sherpa/data/DATA_STRUCTURES_AND_TRANSFORMS.md`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/DATA_STRUCTURES_AND_TRANSFORMS.md)
   * 阐述 Redis 1m 紧凑数组经 `WindowCache` 在内存中滑动维护 200 根的机制，以及 `MarketEvent` 严格按 `-1ms` 推导闭合时刻的因果律设计。
2. **纸面交易标准实现**：[`examples/paper_trading_log_sink.py`](file:///d:/code-repo/Chomo/Sherpa/examples/paper_trading_log_sink.py)
   * 演示如何将 `Runner` 的输出接入 [`LogSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/log_sink.py#L20-L27)，落盘打印携带确定性幂等 key 的标准交易请求。

### 6.3 对应代码模块归属
* **实时流接入**：[`sherpa.data.panel_source.LivePanelSource`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L89-L158)（监听 Redis `stream:market:kline_ready`）。
* **增量滑窗缓存**：[`sherpa.data.window_cache.WindowCache`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/window_cache.py#L18-L67)（内存维护 1m 200 根紧凑数组）。
* **实时调度器**：[`sherpa.strategy.runner.Runner.run_live`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/runner.py#L43-L46)。
* **接收端实现**：[`sherpa.strategy.sink.LogSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/log_sink.py#L20-L27)（记录标准化派发日志）。
* **信号打包层**：[`sherpa.live.request`](file:///d:/code-repo/Chomo/Sherpa/sherpa/live/request.py)（`build_live_requests`、`build_idempotency_key`）。

---

## 7. 阶段四：小资金实盘与阶梯放量 (Canary Live & Scaling)

### 7.1 职责边界与风控规范
* **职责边界**：接入下游真实执行器（Webhooker / Order Manager），使用极小资金进行真实资金通道检验，随后阶梯式放量。
* **核心执行规范**：
  1. **金丝雀首发（Canary Run）**：使用 5,000 ~ 10,000 USDT 小资金实盘试跑 2~4 周；
  2. **执行滑点损耗监测（Execution Drag Analysis）**：
     * 实时统计：$\text{Slip} = \frac{P_{\text{fill}} - P_{\text{signal}}}{P_{\text{signal}}}$；
     * 验证真实执行成本是否在回测预设的 `cost_model` 范围内。若实盘滑点显著高于回测，说明标的流动性不足或发单算法过激，需回退调整；
  3. **阶梯扩容（AUM Scaling）**：若净值曲线与回测偏差 $< 10\%$，按“20% $\to$ 50% $\to$ 100%”按月阶梯注入目标管理规模。

### 7.2 对应代码模块与外部系统边界
* **系统架构总纲**：[`docs/SHERPA_DESIGN.md`](file:///d:/code-repo/Chomo/Sherpa/docs/SHERPA_DESIGN.md)（§7.5 明确 Sherpa 与下游执行系统 Webhooker 的交互接口）。
* **Sherpa 内部边界**：[`sherpa.strategy.sink.WebhookSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/webhook_sink.py#L14-L17)（向外部 Webhooker 发送 HTTP/gRPC 信号，Sherpa 止步于此）。
* **下游系统职责（超出 Sherpa 范围）**：实际报单、挂单撤单追单算法（TWAP/VWAP/POV）、交易所资金清算与保证金对齐。

---

## 8. Sherpa 底层代码模块调用关系矩阵

下表总结了整个生命周期各阶段与 Sherpa 仓库底层代码包的严格对应关系：

| 研发与生产阶段 | 核心任务与输出成果 | 主要涉及的 Sherpa 代码模块 | 核心类 / 函数 / 契约 |
| :--- | :--- | :--- | :--- |
| **阶段一：单因子体检<br>*(Alpha Research)*** | 因子数学实现、全量连续检验、**截面中性化残差化（剔除 Beta/Size 暴露）**、输出各 Regime 下的条件 IC 画像 | `sherpa.alpha`<br>`sherpa.risk`<br>`sherpa.metrics.factor`<br>`research/` | [`Alpha`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/base.py#L12-L50), [`AlphaEngine`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/engine.py#L14-L41), [`ops`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/ops.py)<br>[`rolling_beta`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk/exposure.py), [`neutralize`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk/neutralize.py)<br>[`rank_ic`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/factor.py#L15-L30), [`ic_summary`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/factor.py#L41-L61)<br>`run_screening.py` |
| **三大桥梁关卡<br>*(Portfolio Construction)*** | 因子正交去冗余、基于 Regime 动态合成、资金换手测试 | `sherpa.portfolio`<br>`sherpa.strategy`<br>`sherpa.backtest` | [`demean_l1`](file:///d:/code-repo/Chomo/Sherpa/sherpa/portfolio/weighting.py#L14-L27), [`top_k_long_short`](file:///d:/code-repo/Chomo/Sherpa/sherpa/portfolio/weighting.py#L29-L45)<br>[`BaseStrategy.on_bar`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/base.py#L27-L29)<br>[`drift_weights`](file:///d:/code-repo/Chomo/Sherpa/sherpa/portfolio/turnover.py#L12-L28), [`FixedFeeCostModel`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/cost_model.py#L14-L23) |
| **阶段二：投资组合回测<br>*(Portfolio Backtesting)*** | 多宏观时代全时序切片、事件驱动逐 Bar 撮合、输出综合 PnL 与风控报表 | `sherpa.data`<br>`sherpa.backtest`<br>`sherpa.metrics.performance`<br>`sherpa.strategy` | [`HistoricalPanelSource`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L32-L87)<br>[`Simulator`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/event_driven.py#L34-L100), [`run_vectorized_backtest`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/vectorized.py#L20-L85)<br>[`Runner.run_backtest`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/runner.py#L39-L42), [`BacktestSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/backtest_sink.py#L15-L21)<br>[`sharpe_ratio`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/performance.py#L39-L51), [`max_drawdown`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/performance.py#L53-L59) |
| **阶段三：生产纸面交易<br>*(Paper Trading)*** | 监听真实 Redis 1m 截面通知、验证 500ms 时延与信号幂等性、在线日志校验 | `sherpa.data`<br>`sherpa.live`<br>`sherpa.strategy` | [`LivePanelSource`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L89-L158), [`WindowCache`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/window_cache.py#L18-L67)<br>[`Runner.run_live`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/runner.py#L43-L46), [`LogSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/log_sink.py#L20-L27)<br>[`LiveOrderRequest`](file:///d:/code-repo/Chomo/Sherpa/sherpa/live/request.py#L33-L44), `idempotency_key` |
| **阶段四：小资金与实盘放量<br>*(Live Execution)*** | 派发信号至外部 Webhooker、订单执行算法、实盘滑点基差监控与资金阶梯放量 | `sherpa.strategy.sink`<br>*(下游系统: Webhooker / OM)* | [`WebhookSink`](file:///d:/code-repo/Chomo/Sherpa/sherpa/strategy/sink/webhook_sink.py#L14-L17)<br>*(外部: 限价单/TWAP算法/PMS资金对齐)* |
