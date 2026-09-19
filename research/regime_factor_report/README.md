# Regime Factor Report — 使用与结果解读文档

本工具把机器分析友好的 **long-format 因子体检 CSV** 转换成人更容易阅读的多层报告。

原始输入每一行表示：

> 某个 `alpha` 在某个 `dimension`（regime 维度）的某个 `state` 下的 IC 统计结果。

例如：

- `dimension=trend, state=bear`：熊趋势环境下的因子表现。
- `dimension=volatility, state=high`：高波动环境下的因子表现。
- `state=ALL`：该 dimension 不切 regime 时的基线表现。

工具的目标不是简单找“IC 最大的因子”，而是同时回答：

1. 因子整体有没有信息？
2. 信息方向是正还是负，是否应该反向使用？
3. 因子是否强烈依赖某种 regime？
4. regime 改变时，因子的方向是否发生反转？
5. 极端结果是不是由样本量太小造成的？

---

## 1. 文件结构

```text
regime_factor_report/
├── regime_factor_report.py
├── README.md
└── results/
    ├── 00_dataset_summary.csv
    ├── 01_factor_overview.csv
    ├── 02_dimension_diagnostics.csv
    ├── 03_regime_leaderboard.csv
    ├── 04_regime_matrix.csv
    ├── IMPORTANT_FINDINGS.md
    ├── thresholds.json
    ├── validation.json
    ├── dimensions/
    │   ├── trend_report.csv
    │   ├── volatility_report.csv
    │   ├── dispersion_report.csv
    │   └── liquidity_report.csv
    └── leaderboards/
        ├── trend_bear_top.csv
        ├── trend_bull_top.csv
        ├── ...
        └── volatility_normal_top.csv
```

---

## 2. 运行方法

脚本只使用 Python 标准库，不需要安装 pandas、numpy 等第三方包。

### 最简单运行

在项目目录中：

```bash
python regime_factor_report.py regime_alpha_profile.csv --output-dir results
```

### 指定每个 state 排行榜保留多少个因子

```bash
python regime_factor_report.py regime_alpha_profile.csv \
  --output-dir results \
  --top-n 30
```

参数说明：

- `input_csv`：原始 long-format 因子体检文件。
- `--output-dir`：结果输出目录，默认 `results`。
- `--top-n`：每个单独 state 的排行榜保留多少条，默认 25。

---

## 3. 输入字段要求

必须包含：

| 字段 | 含义 |
|---|---|
| `alpha` | 因子名 |
| `dimension` | regime 维度，例如 trend / volatility |
| `state` | 该维度下的状态，例如 bear / bull / normal |
| `samples` | 有效样本数 |
| `ic_mean` | IC 均值 |
| `ic_std` | IC 标准差 |
| `ic_ir` | `ic_mean / ic_std`；衡量 IC 的稳定强度 |
| `win_rate` | IC 为正（或原统计定义下“胜出”）的比例 |

空指标允许存在。脚本会保留该因子，但将相应部分标记为 Data Quality Issue，而不是直接崩溃。

---

# 4. 脚本模块怎么理解

## 4.1 读取与数据校验

核心函数：

- `load_rows()`
- `validate()`

它们负责：

- 检查必需列是否存在；
- 数字字段转换；
- 空值处理；
- 检查 `(alpha, dimension, state)` 是否重复；
- 统计零样本或缺失指标的行。

结果写入：

- `validation.json`
- `00_dataset_summary.csv`

这是每次分析首先应该检查的数据质量层。

---

## 4.2 自动计算数据集阈值

核心函数：

```python
derive_thresholds()
```

脚本没有把“强因子 = IC_IR > 0.2”这种阈值硬编码进去，而是根据当前数据集的分布生成相对标准。

主要统计：

- `abs_ir_q25`
- `abs_ir_q50`
- `abs_ir_q75`
- `abs_ir_q90`
- `ir_spread_q25`
- `ir_spread_q50`
- `ir_spread_q75`
- `ir_spread_q90`

其中：

```text
abs_ir = |IC_IR|
```

而：

```text
IR spread = max(state IC_IR) - min(state IC_IR)
```

例如 trend：

```text
bear     +0.25
neutral  +0.20
bull     -0.15
```

那么：

```text
IR spread = 0.25 - (-0.15) = 0.40
```

spread 越大，意味着同一个因子对 regime 越敏感。

阈值全部记录在：

```text
results/thresholds.json
```

这样以后换一批 alpha 或换一段时间样本时，分类标准会跟着新数据的分布调整。

---

## 4.3 为什么强度使用 `abs(IC_IR)` 排序

因子体检阶段应该区分两个概念：

### 信息强度

```text
|IC_IR|
```

越大代表信号越强、越稳定。

### 信息方向

```text
IC_mean >= 0  -> original
IC_mean < 0   -> invert
```

负 IC 不等于“没有 alpha”。例如：

```text
IC_IR = -0.30
```

可能意味着这是一个很稳定的反向信号。

因此结果中同时保留：

- `ic_ir`
- `abs_ic_ir`
- `direction`

不要仅仅因为 IC 是负数就把它当作坏因子。

---

## 4.4 Dimension-level regime 分类

核心函数：

```python
classify_dimension()
```

它针对：

```text
一个 alpha + 一个 dimension
```

例如：

```text
alpha088 + trend
```

一起比较 `bear / neutral / bull` 三个 state。

脚本给出六种标签。

### `Weak / Noise`

该 dimension 中最强 state 的 `|IC_IR|` 仍低于全数据非 ALL 状态的中位数。

含义：

> 暂时没有明显信息优势。

---

### `Regime-Reversal`

不同 regime 中存在**有实质强度的正负方向反转**，并且 IR spread 位于数据集较高区间。

脚本并不是只要出现：

```text
+0.001 -> -0.002
```

就说 reversal。

为了避免零附近噪声，正负两侧都必须至少超过当前数据 `|IC_IR|` 的 25% 分位阈值。

这是非常值得研究的一类：

> regime 不只是改变 alpha 强弱，而可能改变 alpha 的经济方向。

---

### `Conditional`

没有达到 material reversal，但：

- 某些 regime 中信号很强；
- state 之间的 spread 很大。

这通常意味着：

> 因子适合做 regime gating 或 regime weighting。

例如只在 liquidity-starved 环境开启，其他时候降低权重。

---

### `Stable`

各 state：

- 方向一致；
- IR spread 很小；
- 整体强度不弱。

这种因子更接近：

> regime-independent / unconditional alpha。

---

### `Mixed / Moderate`

有一定差异，但不足以明确归到上面的极端类型。

它不是坏标签，只代表：

> 暂时没有足够强的证据把它定义为稳定、条件化或反转因子。

---

### `Data Quality Issue`

该 alpha/dimension 没有可用数据。

首先检查数据生成过程，而不是解释 alpha 本身。

---

# 5. 样本量保护

强烈建议每次看排行榜时都一起看：

```text
low_sample
```

脚本默认满足任意一个条件即标记为 low sample：

```text
samples < 100
```

或者：

```text
samples / ALL_samples < 10%
```

原因是极端 regime 往往数量很少，因此可能产生看起来非常夸张的 IC_IR。

比如某个 state：

```text
samples = 54
IC_IR  = 0.80
```

它很值得进一步研究，但不能与：

```text
samples = 900
IC_IR  = 0.35
```

简单地认为前者“更可靠”。

本工具不会自动用样本量去修改 IC_IR，因为那会引入额外统计假设；它选择更透明的处理方式：

> 保留原结果 + 显式风险标记。

---

# 6. 结果文件逐个怎么读

## 6.1 `00_dataset_summary.csv`

用途：**先确认这次体检的数据是否完整。**

包含：

- 输入行数；
- alpha 数量；
- dimension 数量；
- 缺失数据量；
- 本批数据自动生成的分类阈值；
- 各 dimension 的 state 集合。

每次换数据后建议先看这一份。

---

## 6.2 `01_factor_overview.csv`

用途：**主入口，一行一个因子。**

这是平时最应该先打开的表。

关键字段：

### `factor_classification`

因子级别的总分类。

优先级逻辑大致是：

```text
如果任一 dimension 是 Regime-Reversal
=> factor = Regime-Reversal

否则如果任一 dimension 是 Conditional
=> factor = Conditional

否则再判断 Stable / Weak / Mixed
```

这意味着 overview 更偏向发现“需要注意的 regime 行为”，而不是给因子做最终投资评级。

### `baseline_ic_*_median`

每个 dimension 的 `ALL` 记录可能略有差异，因此脚本不假设某一行天然是唯一 overall baseline，而是取四个 dimension ALL 的中位数作为稳健摘要。

### `best_regime_dimension / best_regime_state`

寻找全体非 ALL state 中：

```text
|IC_IR|
```

最大的 state。

同时检查：

```text
best_regime_low_sample
```

### `most_sensitive_dimension`

哪个 dimension 的：

```text
max(IC_IR) - min(IC_IR)
```

最大。

比如：

```text
most_sensitive_dimension = liquidity
```

则优先去：

```text
results/dimensions/liquidity_report.csv
```

查看这个因子的具体状态差异。

### `regime_reversal_dimensions`

例如：

```text
trend|liquidity
```

表示这个因子在这两个 regime 维度中都发生了有实质强度的方向反转。

---

## 6.3 `02_dimension_diagnostics.csv`

用途：**一行 = 一个 alpha × 一个 dimension。**

这是解释 regime dependency 最关键的一张表。

重要字段：

- `classification`
- `ir_spread`
- `max_abs_ir`
- `median_abs_ir`
- `sign_flip`
- `material_sign_flip`
- `best_state`
- `best_state_ic_ir`
- `best_state_direction`
- `best_state_low_sample`
- `low_sample_states`

### `sign_flip` vs `material_sign_flip`

`sign_flip=True`：数学上出现过正负号变化。

`material_sign_flip=True`：正负两侧都达到一定信息强度，因此方向变化更值得解释。

真正做 regime reversal 研究时优先看后者。

---

## 6.4 `dimensions/*.csv`

用途：**人眼横向比较同一个 dimension 下所有 state。**

例如：

```text
trend_report.csv
```

会把原来的：

```text
alpha001 trend ALL
alpha001 trend bear
alpha001 trend bull
alpha001 trend neutral
```

横向铺成一行。

因此你可以直接比较：

```text
bear_ic_ir
neutral_ic_ir
bull_ic_ir
```

而不需要上下找四行。

表格默认优先把：

1. Regime-Reversal
2. Conditional
3. Stable
4. Mixed
5. Weak
6. Data Quality Issue

放在前面；同类中再按照 regime sensitivity 排序。

这是最适合人工研究具体 dimension 的输出。

---

## 6.5 `03_regime_leaderboard.csv`

用途：回答：

> “某个具体 regime 中哪些 alpha 信息最强？”

排序主体是：

```text
|IC_IR| DESC
```

并保留：

```text
direction
```

所以：

```text
IC_IR = -0.4
```

不会因为负号被扔到榜尾。

同时 `low_sample=False` 的记录优先于小样本记录。

---

## 6.6 `leaderboards/*.csv`

这是 `03_regime_leaderboard.csv` 的方便阅读拆分版。

例如：

```text
trend_bear_top.csv
liquidity_starved_top.csv
volatility_high_top.csv
```

当你只研究一个 regime 时直接打开对应文件。

---

## 6.7 `04_regime_matrix.csv`

用途：**统一跨维度状态策略装配总表（Dimension × State 作战矩阵）。**

该表直接聚合了所有 12 个细分状态下的 Top 3 最强 Alpha，并自动标注了：
- **交易方向与带符号因子名**（例如 `+worldquant.alpha026`, `-worldquant.alpha007`）；
- **样本数与小样本警示**（`samples`, `low_sample`）；
- **Top 1 ~ Top 3 的各自信噪比与胜率**（`ic_ir`, `abs_ic_ir`, `win_rate`）；
- **简明摘要字段**（`top_signed_alphas` 与 `top_alphas_summary`）。

量化策略层（如 `BaseStrategy.on_bar`）可直接读取此表实现状态自适应动态多因子路由。

---

## 6.8 `IMPORTANT_FINDINGS.md`

这是脚本自动生成的文字摘要。

它会列出：

- 数据质量；
- 当前数据集阈值；
- 各分类数量；
- regime sensitivity 最大的一批 factor/dimension；
- 排除 low-sample 后最强的 state-level 因子；
- 看起来很强、但其实是 low-sample 的结果。

建议每次运行后先读它，再进入 CSV 细节。

---

# 7. 推荐的人类阅读流程

不要从 1300 多行原始 long-format 文件开始浏览。

推荐：

### Step 1 — 数据质量

打开：

```text
00_dataset_summary.csv
IMPORTANT_FINDINGS.md
```

先检查缺失和样本量。

### Step 2 — 找值得研究的因子

打开：

```text
01_factor_overview.csv
```

重点看：

```text
Regime-Reversal
Conditional
```

以及：

```text
max_ir_spread
```

### Step 3 — 判断是哪个 regime 在驱动

打开：

```text
02_dimension_diagnostics.csv
```

例如发现：

```text
alpha007 + liquidity = Regime-Reversal
```

就继续进入 liquidity 宽表。

### Step 4 — 横向读具体状态

打开：

```text
dimensions/liquidity_report.csv
```

直接比较：

```text
high / normal / starved
```

对应的：

```text
IC mean
IC IR
win rate
samples
```

### Step 5 — 策略层面再决定怎么使用

典型逻辑：

```text
Stable
→ 可考虑常驻基础权重

Conditional
→ regime gating / dynamic weighting

Regime-Reversal
→ 不仅调权，甚至可能需要按 regime 改变方向

Weak / Noise
→ 暂时降低研究优先级
```

这些只是研究工作流，不是自动交易规则。真正使用前仍要做 out-of-sample、交易成本、相关性和稳定性检验。

---

# 8. 一个重要统计注意事项

本报告是 **exploratory factor diagnostics**，不是显著性检验。

`IC_IR = ic_mean / ic_std` 并不自动等价于独立同分布样本下的传统 t-stat。

特别是时间序列通常存在：

- 自相关；
- regime persistence；
- overlapping horizon；
- 多重检验；
- 因子间相关性。

因此不要根据单次高 IC_IR 就直接得出“可交易”的结论。

下一层正式研究通常应该增加：

1. walk-forward / OOS 稳定性；
2. bootstrap 或 HAC/Newey-West 风格稳健误差；
3. multiple-testing correction；
4. turnover / transaction cost；
5. factor correlation / redundancy；
6. regime transition 前后的稳定性。

---

# 9. 为什么保留原始 long-format 文件

原始文件仍然是最适合程序处理的数据结构。

本脚本生成的文件属于：

> presentation / diagnostic layer

而不是替代原始数据。

推荐架构：

```text
raw long-format CSV
        ↓
regime_factor_report.py
        ↓
人类阅读的 overview / dimension wide tables / leaderboard
        ↓
研究结论
        ↓
新的策略实验
```

这样原始统计逻辑与人类分析层是分离的，可复现性更好。
