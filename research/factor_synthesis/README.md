# Factor Synthesis — 三大工程关卡 · 关卡2（执行文档 / 架构设计）

对应 [`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`](../../QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md) §4
「关卡 2：基于微观 Regime 的动态多因子合成 (Synthesis)」。

> **状态：设计阶段。** 已有入口脚本 `refresh_candidates.py`（把关卡1 的 keep 名单写进 `config.py`），
> 合成本身尚无代码。本文先把架构、输入输出契约、验证方法和执行步骤定下来，代码按 §9 的里程碑逐步落地。

---

## 1. 这一关要回答什么

关卡1 给出的是：**每个 regime state 下，一组互不冗余的残差因子**（已剥离 Beta/Size，已去冗余）。
关卡2 要回答：

> 在每一根 bar 上，把这些因子**合成为一个分数** `score(t, symbol)`，并证明这个合成分数
> **在样本外比简单做法更好**。

它的产出是一张 `(T, N)` 的合成分数矩阵。这张矩阵：
- 会被**当作一个新因子**，再用阶段一的同一套指标体检一遍（IC / IC_IR / Regime 条件 IC）；
- 会交给关卡3，映射成持仓权重后做摩擦和容量测试；
- 最终以同样的逻辑出现在实盘策略 `BaseStrategy.on_bar` 里（离线和在线必须一致，见 §8）。

本关**不负责**：
- 手续费 / 滑点 / 容量：那是关卡3。本关只做一个粗略的换手观察，作为早期预警；
- 最终持仓权重的优化：先直接用现有的 `demean_l1` / `top_k_long_short`。

---

## 2. 输入与输出契约

| 项 | 来源 | 说明 |
|---|---|---|
| 候选因子（per state） | 关卡1 的 `02_regime_cluster_assignments.csv` 里 `recommendation=keep` 的因子 | 沿用 research 子目录之间"上游结果 CSV → 下游 config.py"的通信方式：由 `refresh_candidates.py` 写进本目录 `config.py` 的 `REGIME_FACTOR_SETS`（`run_research.sh --refresh-synthesis-candidates`，步骤 8）；合成代码运行时只读 `config.py`，不直接读关卡1 的 CSV。读取规则和理由见该脚本的 docstring |
| 因子历史分数 | `sherpa.alpha.registry` 按 qualified_name 计算 → 掩码 → `neutralize()` 残差化 | 和关卡1 `_resolve_histories()` 完全相同的处理顺序 |
| Regime 标签 | `sherpa.backtest.regime_screening.regime_report` | 和阶段一、关卡1 同一套定义；逐 bar、Point-in-time（滚动分位数，无前视） |
| 时间窗 / 标签 | [`research/research_config.json`](../research_config.json) | 所有研究只用研究段；holdout 段的用法见 §6.4。IC 标签口径（持有期、执行延迟）也从这里读，跟阶段一、关卡1 一致 |
| **输出** | `results/` 下的 CSV（见 §7） | 各方案的合成 IC 对比、权重表、walk-forward 明细 |

---

## 3. 核心设计难点：一根 bar 同时属于 4 个 state

这是动手前必须先想清楚的问题。

`regime_report` 输出的是 **4 个独立维度**（trend / volatility / dispersion / liquidity），每个维度 3 档。
关卡1 也是**按维度分别**给出候选集的。因此在任意一根 bar 上，市场**同时**处在 4 个 state 里，例如：

```text
t = 2025-03-10 08:00   trend=bear  volatility=high  dispersion=normal  liquidity=normal
                          ↓             ↓                 ↓                  ↓
                     trend.bear 的   volatility.high   dispersion.normal   liquidity.normal
                     因子集 + 权重    的因子集 + 权重     的因子集 + 权重       的因子集 + 权重
```

4 组权重同时"命中"，必须决定怎么合并成一组。可选方案：

| 方案 | 做法 | 优点 | 缺点 | 结论 |
|---|---|---|---|---|
| **A. 单一主维度路由** | 只选一个维度（比如 volatility）做路由，其余维度不参与 | 最简单、最好解释、自由度最低 | 丢掉其它维度的信息 | **首选起点** |
| **B. 多维度平均** | 4 个 state 各自给出一个因子权重向量，4 个向量取平均（或按各 state 的 IC_IR 加权） | 用上全部维度；天然平滑（单一维度切换只改变 1/4 权重） | 解释性变差；维度之间信息重叠 | **作为 A 的对照** |
| C. 联合 state | 用 4 维拼接的 `regime_label`（最多 81 种组合）单独估权重 | 理论上最精细 | 大部分组合样本极少，必然过拟合 | **不采用** |
| D. regime 作为模型特征 | 让模型学 `w = f(regime one-hot)` | 最灵活 | 需要 ML 基建和更严格的验证 | 里程碑 M5 以后 |

**主维度怎么选**（方案 A）：看阶段一 `regime_alpha_profile.csv` 里哪个维度的"各 state 条件 IC_IR 差异"最大。
差异越大，说明这个维度对"该用哪些因子"影响越大。这一步有数据支撑，不凭感觉拍。

---

## 4. 合成方案的阶梯：每一级都必须打赢上一级

业内的硬规矩（[`docs/factor_mining_landscape.md`](../../docs/factor_mining_landscape.md) §5.4、
[`docs/factor_mining_topic.md`](../../docs/factor_mining_topic.md) §6）：**任何复杂的合成方法都必须先打赢等权和 ICIR 加权基线。**
所以关卡2 按阶梯推进，复杂度一级级往上加，每一级都要在样本外证明比下一级更好：

| 级别 | 名称 | 权重怎么来 | 用不用 regime |
|---|---|---|---|
| **L0** | 等权基线 | 全部保留因子（各 state 保留名单的并集）方向对齐后等权 | 否 |
| **L1** | 静态 ICIR 加权 | 训练段上每个因子全历史的 IC_IR 作为权重 | 否 |
| **L2** | Regime 路由（硬切换） | 当前 state 下，用该 state 条件 IC_IR 作为权重，只用该 state 的保留因子 | 是 |
| **L3** | Regime 路由 + 平滑 | L2 的基础上加迟滞 / 权重平滑（§5.3），避免 state 边界来回翻转 | 是 |
| L4 | ML 合成（以后） | Ridge / LightGBM，因子 + regime 作为特征 | 是 |

**如果 L2/L3 打不赢 L1，结论就是"regime 路由在当前因子池上不值得"**，直接用 L1 进关卡3。
这是一个正常、有价值的结论，不是失败。

---

## 5. 合成的具体计算

### 5.1 合成前的预处理（逐期截面）

对每个因子的残差分数，逐个时间戳：

1. **截面标准化**：截面 rank 映射到 [-0.5, 0.5]（或 z-score + 去极值）。不同因子量级差异很大，
   不统一就加权，权重没有意义。
2. **方向对齐**：乘以该因子（在该 state 下）的 IC 符号，让所有因子都是"分数越高、未来收益越高"。
   L2/L3 里同一个因子在不同 state 下的方向**可能相反**，所以方向要按 state 取。

### 5.2 权重估计

- **L1**：`w_i = IC_IR_i / Σ|IC_IR_j|`，只用训练段数据估计。
- **L2**：`w_i^(s) = IC_IR_i^(s) / Σ|IC_IR_j^(s)|`，`s` = 当前 state，只在训练段里属于 `s` 的 bar 上估计。
- **小样本 state 的收缩（shrinkage）**：样本少的 state（例如之前只有 54 个样本的 `trend.bull`），
  条件 IC_IR 本身就很不可靠。按样本量把它往 L1 的全局权重拉：

  ```text
  λ_s   = n_s / (n_s + n_0)          n_s = 该 state 训练样本数，n_0 = 收缩强度（比如 200 根 bar）
  w^(s) = λ_s · w_state + (1 − λ_s) · w_global
  ```

  样本越多越信任 state 专属权重，样本越少越接近全局权重。这比直接丢掉小样本 state 更平滑。

### 5.3 平滑过渡（L3）

LIFECYCLE 的要求：严禁在相邻两期做"非 0 即 100%"的剧烈翻转。两种做法任选或叠加：

- **状态确认（hysteresis）**：新 state 必须连续出现 `m` 根 bar（比如 `m = 3`）才切换，否则沿用旧 state；
- **权重指数平滑**：`w_t = β · w_{t−1} + (1 − β) · w_target(t)`，`β` 越大越平滑。

两者都只用 ≤ t 的信息，不引入前视。`m` 和 `β` 是新增的超参数，同样只能在训练段上选。

### 5.4 合成

```text
score(t, ·) = Σ_i  w_i(t) · 标准化并方向对齐后的 f_i(t, ·)
```

合成后再做一次截面 rank，作为最终输出，喂给阶段一的体检函数和关卡3。

---

## 6. 验证方法：防止"在同一段数据上既选因子又调权重"

这是关卡2 最容易自欺的地方：阶段一在研究段上选了因子，关卡1 在研究段上去了冗余，
如果关卡2 还在**同一段数据**上拟合权重、再在**同一段数据**上看效果，得到的合成 IC 一定虚高。

### 6.1 Walk-forward（滚动前推）

在研究段内部按时间滚动：

```text
|—— 训练窗 ——|gap|— 测试 —|
      |—— 训练窗 ——|gap|— 测试 —|
            |—— 训练窗 ——|gap|— 测试 —|   ……
```

- 每次只用训练窗估计权重（L1/L2 的 IC_IR、收缩系数），应用到紧随其后的测试段；
- 拼接所有测试段的合成分数，得到一条**全部由样本外预测构成**的序列，再算它的 IC / IC_IR；
- 训练窗建议用**扩展窗**（从研究段起点到当前），重估频率按月（约 180 根 4h bar）。

### 6.2 Purge + Embargo（清洗 + 隔离带）

- 标签是下一根 bar 的收益（`h = 1`），训练窗最后 `h` 根 bar 的标签会和测试段重叠，必须删掉（purge）；
- 在训练窗和测试段之间再留 `gap ≥ h` 根 bar 的隔离带（embargo）；
- 以后如果换成更长的预测周期（比如 6 根 bar = 1 天），`gap` 跟着变大。

### 6.3 要比较的指标

所有方案（L0~L3）都基于 walk-forward 拼出来的样本外序列，比较：

| 指标 | 复用 | 说明 |
|---|---|---|
| 合成 IC 均值 / IC_IR / 胜率 | `sherpa.metrics.factor.ic_summary` | 主判据 |
| Regime 条件 IC | `conditional_ic_summary` | L2/L3 是否真的在"该发挥的 state"里更好 |
| 分组单调性 | `quantile_returns` + `is_monotonic_decreasing` | 合成分数的排序是否整齐 |
| 分数稳定性（换手预警） | 相邻两期合成分数的截面 rank 自相关 | 越低说明换手越高，关卡3 会更吃亏 |
| 粗略扣费回测（可选） | `run_vectorized_backtest` + `demean_l1` + `FixedFeeCostModel` | 只做早期预警，正式结论在关卡3 |

**验收规则**：L_k 被采纳，当且仅当它在样本外合成 IC_IR 上**明显**高于 L_{k−1}（建议起点：高 10% 以上），
**并且**分数稳定性没有明显恶化。仅仅"略好一点"不值得多出来的自由度。

### 6.4 Holdout 的使用规矩

`research_config.json` 的 `window` 里 `research_end ~ holdout_end`（2026-03-15 ~ 2026-09-15）这一段：

- 阶段一、关卡1、关卡2 的所有选择和调参都**不碰**它；
- 关卡2 选定最终方案（包括超参数）之后，才在 holdout 上**跑一次**，记录结果，不再回头调参；
- 如果 holdout 上明显失效，正确的做法是**回到研究段重新思考**，而不是换一组参数再在 holdout 上试。
  反复在 holdout 上试，它就不再是样本外了；
- **取数时注意 warm-up**：因子和 regime 需要回看历史（regime 默认 120 根 bar），holdout 取数要从
  `research_end` 往前多取一段作为预热，但**只在 bar 时间 > `research_end` 的部分**计算指标。
  `CHReader.fetch_history` 的起止时间是闭区间，边界上那根 bar 会同时落在两段里，要用严格大于来切。
- holdout 的取数函数等到真正需要时再加到本目录的 `data.py`（`load_holdout_panel()`），现在不做。

---

## 7. 计划中的目录结构

```text
factor_synthesis/
├── README.md                 本文件
├── config.py                 【已有】候选因子 REGIME_FACTOR_SETS（由 refresh_candidates.py 自动刷新）；
│                             以后再加：主维度、收缩强度 n_0、平滑参数 m / β、walk-forward 参数
├── refresh_candidates.py     【已有】读关卡1 的 02_regime_cluster_assignments.csv，重写 config.py 的候选池
├── data.py                   取数入口（按 research 约定自成一份；时间窗与标签读 research_config.json）
├── signals.py                纯函数：截面标准化、按 state 方向对齐
├── weighting.py              纯函数：L0 / L1 / L2 / L3 的权重计算，收缩，迟滞与平滑
├── walk_forward.py           纯函数：切分训练 / 测试窗（含 purge + embargo），拼接样本外合成分数
├── run_synthesis.py          主脚本：取数 → 残差化 → 打标 → 各方案 walk-forward → 对比 → 落盘
└── results/
    ├── 01_scheme_comparison.csv       每个方案一行：样本外 IC / IC_IR / 胜率 / 分数稳定性 / 粗略净 Sharpe
    ├── 02_conditional_ic_by_scheme.csv 方案 × regime state 的条件 IC
    ├── 03_weights_by_state.csv         最后一个训练窗估出的权重（用于解读，也是将来实盘用的权重）
    └── 04_walk_forward_detail.csv      每个 walk-forward 窗口的训练区间、测试区间、测试段 IC
```

`signals.py` / `weighting.py` / `walk_forward.py` 刻意写成**只吃 pandas、不碰 IO 的纯函数**，原因见 §8。

---

## 8. 和实盘的关系：合成逻辑以后要搬进 `sherpa`

关卡2 选定的合成方法，最终会在实盘 `BaseStrategy.on_bar` 里逐 bar 执行。阶段三（纸面交易）有一条硬指标：
**离线回测信号和在线信号逐笔对齐，相关系数必须等于 1.000**。因此：

- 合成逻辑（标准化、方向对齐、路由、平滑）属于**决策逻辑**，必须做到"一份代码，回测和实盘共用"。
  它不能只活在 `research/` 的脚本里；
- 所以本目录的纯函数从一开始就要写成**可以直接搬走**的形式：只依赖 pandas/numpy，输入输出都是
  `(T,N)` 矩阵或单个截面，不依赖 research 的配置和 IO；
- 平滑和迟滞需要记住上一期的状态。纯函数要把"上一期状态"作为显式参数传入、显式返回，
  不用隐藏的全局变量。这样批量回测（整段矩阵）和实盘（逐 bar）才能共用同一个实现；
- 等关卡2、关卡3 的结论稳定后，再把这几个函数迁移到 `sherpa`（候选位置：`sherpa.portfolio`
  下新增一个合成模块），研究脚本改为 import 它。

---

## 9. 执行步骤（里程碑）

前置：先用新时间窗（2020-01-01 ~ 2026-03-15）重跑阶段一和关卡1（`run_research.sh --refresh-candidates`），
确认新的保留名单。

- [x] **M0 入口**：`config.py` + `refresh_candidates.py`，关卡1 的 keep 名单自动写进候选池（`run_research.sh` 步骤 8）
- [ ] **M0 准备**：建 `data.py`；
      用阶段一的条件 IC 表选出主维度（§3），把选择依据写进 `config.py` 注释
- [ ] **M1 基线**：`signals.py` + L0、L1 + `walk_forward.py`（含 purge/embargo）+ `01_scheme_comparison.csv`。
      L0/L1 的样本外 IC_IR 是之后所有方案的及格线
- [ ] **M2 Regime 路由**：L2（方案 A 主维度路由）+ 小样本收缩 + `02_conditional_ic_by_scheme.csv`；
      同时做方案 B（多维度平均）作为对照
- [ ] **M3 平滑**：L3（迟滞 / 指数平滑），观察分数稳定性的改善和 IC 的代价
- [ ] **M4 定稿 + 交接**：按 §6.3 的验收规则选定方案 → 在 holdout 上跑一次 → 输出最终权重表 →
      交给关卡3 做摩擦和容量测试
- [ ] **M5（以后）**：L4 ML 合成（Ridge 起步，再 LightGBM；必须打赢 L1），可接关卡1 的使用层增量检验
- [ ] 每个纯函数配单测：合成数据构造"只在某个 state 有效的因子"，验证 L2 能识别、L0/L1 不能；
      验证 walk-forward 切分里训练窗永远不包含测试段及其 gap

---

## 10. 风险清单

| 风险 | 表现 | 对策 |
|---|---|---|
| 路由自由度过拟合 | 12 个 state × 5 个因子 = 60 个权重，研究段内 IC 很漂亮，样本外平庸 | walk-forward 只看样本外；小样本收缩；必须打赢 L1 |
| 小样本 state | 条件 IC_IR 的估计噪声远大于信号 | 收缩到全局权重；`low_sample` 标记沿用阶段一口径 |
| state 边界抖动 | regime 在两档之间来回切，权重跟着翻转，换手暴增 | L3 迟滞 / 平滑；关注分数稳定性指标 |
| 同一份数据用三次 | 阶段一选因子、关卡1 去冗余、关卡2 调权重都用研究段 | walk-forward 只能缓解，不能根除；holdout 一次性验收兜底 |
| 离线 / 在线不一致 | 研究脚本和实盘策略各写一份合成逻辑 | §8：纯函数 + 显式状态，稳定后迁移进 `sherpa` |
| regime 标签本身的滞后 | 滚动分位数判出 state 时，行情可能已经走了一段 | 这是 regime 定义的固有属性，在条件 IC 里已经如实体现；不要为了"更及时"引入任何前视信息 |
