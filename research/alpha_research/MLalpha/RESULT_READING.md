# MLalpha 结果阅读指南（ML alpha 研究的主框架）

一个 ML alpha（或任何新的打分）到底行不行，按本文的顺序读结果、按本文的标准下结论。之后所有 ML alpha 研究（新特征、
新模型、NN……）都用这一套，跟基线 `LgbmV2` 比。

设计和代码见 [`sherpa/alpha/custom/ML_ALPHA_DESIGN.md`](../../../sherpa/alpha/custom/ML_ALPHA_DESIGN.md)、
[`research/ml_training/README.md`](../../ml_training/README.md)；关卡3 其它表（00 ~ 03、case_grids）的细节见
[`research/friction_test/RESULT_READING.md`](../../friction_test/RESULT_READING.md)。

---

## 1. 先分清几个词

| 词 | 指什么 | 例子 |
| --- | --- | --- |
| **模型 / alpha** | 一个注册的打分来源 | `custom.ml_lgbm_v2` |
| **种子集成** | 每个重训时点训练多个随机种子的模型，推断时**取平均**成一份打分。对后面所有评估来说，一个 alpha 就是**一份**打分，种子不是单独的样本 | V2：9 个种子 |
| **case** | 关卡3 里的一行配方 = 一个打分来源。单模型研究线透传后就是 `single:<alpha>`，外加等权混合 `直通·G0` 等 | `single:custom.ml_lgbm_v2` |
| **组合** | 把**同一份**打分变成仓位的一种具体方式 = 映射 × 调仓频率。现在 13 种映射 × 3 种调仓频率 = **39 个组合** | `q10_exit30`，每 3 根调仓 |
| **映射** | 每边选几个币、迟滞多宽。`top10_exit50` = 绝对名次（前 10 开仓、跌出前 50 平仓）；`q10_exit30` = 相对分位（前 10% 开仓、跌出前 30% 平仓，币池大小变了含义不变） | |
| **段** | 选择段 `2023-01-01 ~ 2024-06-30`（ML 模型从 2023-06-30 起才有打分，评估从第一根有打分的 bar 算起）；验证段 `2024-06-30 ~ 2026-03-15`；holdout 不碰 | `research_config.json` |
| **成本** | `zero`（毛收益）/ `all_maker`（全挂单 2 bps，乐观）/ `all_taker`（全吃单 5 + 3 = 8 bps，**主口径**）/ `stress`（吃单 + 大滑点） | |

**一个组合在一个段上只有一个 Sharpe**（用这一段所有 bar 的逐 bar 净收益算）。所谓"中位数"，是同一个 case 的 39 个组合
的 Sharpe 取中位数——不是跨种子、也不是跨时间。

---

## 2. 一次运行的产出在哪

```text
research/alpha_research/MLalpha/
  models/<模型名>/manifest.json                    每个重训时点的模型、早停轮数、内部验证 IC_IR
  results_without_neutralization/
    ml_training/<模型名>_folds.csv                 第 0 步：训练自检（每个重训时点）
    ml_training/<模型名>_oos_summary.csv           第 0 步：拼起来的样本外 RankIC
    report/                                       阶段一体检（按 regime 切片的 IC，诊断用）
    friction/04_robustness.csv                    ★ 第 1 步：稳健性
    friction/06_quarterly.csv                     ★ 第 2 步：分季度稳定性
    friction/05_style_attribution.csv             ★ 第 3 步：风格归因
    friction/02_validation_base_cost.csv          第 4 步：具体组合排名
    friction/case_grids/<case>.csv                第 4 步：一个 case 的二维截面
```

跑法：`bash research/alpha_research/MLalpha/run_track.sh`（训练是增量的；改了特征或训练配置要先
`python research/ml_training/run_training.py --track MLalpha --force`）。

---

## 3. 阅读顺序

### 第 0 步：训练自检（`ml_training/`）——只用来排除"训练出了问题"

- `<模型名>_oos_summary.csv`：样本外 RankIC 应该为正、两段量级相近。
- `<模型名>_folds.csv`：`best_iterations` 太多是 1（第一棵树就早停）说明后面的树学不到东西；`inner_valid_ic_ir` 忽高忽低是正常的（噪声大）。

**不要用 RankIC 判断好坏。** 第一版 RankIC 0.056 却不赚钱：排名类指标奖励"中位数效应"（高波动币大多数时候排名靠后，但平均收益
不低），Top-K 等权赚的是平均收益。另外 V2 的训练标签持有 6 根，它的 RankIC 是对 6 根收益算的，跟持有 1 根的 V1 不可比。

### 第 1 步：`04_robustness.csv` —— 这个打分换一种合理的交易方式还赚不赚钱（**最核心**）

每个 case × 成本一行：

| 列 | 含义 |
| --- | --- |
| `n_combos` | 计入的组合数（选择段空仓 > 20% 的组合剔除——它的 Sharpe 是在很少的交易 bar 上算的） |
| `selection_median` / `validation_median` | 39 个组合在该段的扣费净 Sharpe 中位数 |
| `selection_positive_frac` / `validation_positive_frac` | 该段净 Sharpe > 0 的**组合**占比 |
| `both_positive_frac` | **两段都 > 0 的组合占比**——最能说明问题的一个数 |

怎么读：

- **先看 `all_taker` 行**（主口径）。`both_positive_frac` 高、两段中位数都 > 0，才说明"信号本身有"，而不是某一种映射碰巧好；
- 再看 `all_maker` 行：吃单不行、挂单行，说明边际存在但被成本吃掉，方向是降换手 / 改执行；
- 再看 `zero`（毛收益）：毛收益都不行，就是信号本身弱，跟成本无关；
- **只看网格里最高的那一格会自欺**：39 个数里挑最大的，天然挑到运气最好的那个（探索实验里选择段最好的格子到验证段大多不成立）。

### 第 2 步：`06_quarterly.csv` —— 是不是靠一两个季度撑起来的

每个 (case, 映射, 调仓频率) 一行，吃单净收益：

| 列 | 含义 |
| --- | --- |
| `quarters` | 计入的季度数（不足 60 根 bar 的零头季度不计） |
| `positive_quarter_frac` | 赚钱季度的占比 |
| `sharpe[2024Q3]` … / `return[2024Q3]` … | 各季度的净 Sharpe / 收益 |

04 是"横向换交易方式"，06 是"纵向换时间"。一个真正的边际应该在大多数季度为正，而不是一两个季度贡献大部分收益。
看法：对 04 里表现好的那片组合，看它们的 `positive_quarter_frac`，再看是哪几个季度亏、亏得是否集中。

### 第 3 步：`05_style_attribution.csv` —— 赚的是选币能力还是风格

每个 (case, 映射, 调仓频率) × 段一行：吃单净收益对 6 个风格收益做时间序列回归
`r_t = α + Σ β_j · f_j,t + ε_t`。风格收益是用同一个回测器构造的简单多空组合：

| 风格 | 做多 / 做空 |
| --- | --- |
| `btc` | BTC 自己 |
| `market` | 掩码内全部币等权（山寨币整体） |
| `low_vol` | 近 42 根波动最低 20% / 最高 20% |
| `small_size` | 近 42 根成交额最小 20% / 最大 20% |
| `reversal` | 近 6 根跌最多 20% / 涨最多 20% |
| `momentum` | 近 120 根涨最多 20% / 跌最多 20% |

| 列 | 怎么读 |
| --- | --- |
| `beta[*]` | 风格暴露。`beta[low_vol]` 明显为正 = 收益有一部分只是"买低波动、卖高波动"，用一条规则就能复制 |
| `r2` | 风格能解释的方差比例 |
| `raw_sharpe` | 原始净 Sharpe（同 04 的那个数） |
| `alpha_sharpe` | **剥离风格后**（`r − Σβ·f`）的 Sharpe = 选币能力的估计 |
| `alpha_t` | α 的 t 值（普通 OLS，没做自相关修正，偏乐观，只作参考） |

只对 BTC 回归（`beta[btc]` ≈ 0）只排除了"押大盘方向"一种解释，低波动 / 反转这些跟大盘无关的风格要一起看。

### 第 4 步：`02_validation_base_cost.csv` / `case_grids/`

前三步确认"这个打分值得用"之后，才来这里挑具体的映射和调仓频率。挑的时候选**一片都不错的区域的中间**，不要选孤立的最高点。

### 第 5 步：跟基线比

固定同一套网格、同一个起点，跟 §5 的 `LgbmV2` 数字逐项比：04 的两段中位数和 `both_positive_frac`、06 的
`positive_quarter_frac`、05 的 `alpha_sharpe`。只有这几项一起更好，才算新模型更好。

---

## 4. 判断标准速查

| 问题 | 在哪看 | 建议门槛 |
| --- | --- | --- |
| 训练有没有出问题 | `ml_training/*_oos_summary.csv` | 两段样本外 RankIC 都为正 |
| 信号本身强不强 | 04 的 `zero` 行 | 两段毛 Sharpe 中位数明显 > 1 |
| 扣费后能不能赚钱 | 04 的 `all_taker` 行 | **两段中位数都 > 0，`both_positive_frac` ≥ 0.5** |
| 成本多敏感 | 04 的 `all_maker` / `stress` 行、02 的 `breakeven_cost_bps` | 保本成本明显高于 8 bps |
| 时间上稳不稳 | 06 的 `positive_quarter_frac` | 稳健区域的组合 ≥ 0.6 |
| 是不是选币能力 | 05 的 `alpha_sharpe`、`alpha_t`、`beta[*]` | `alpha_sharpe` 中位数 > 0.5，风格 β 不主导收益 |
| 能不能进阶段二 | 全部 + 关卡3 红线 | 吃单验证段净 Sharpe ≥ 2.5、换手衰减 < 40%，且上面各项通过，最后 holdout 只跑一次 |

门槛是 2026-10-05 定的经验值，第一版基线还没全部达到；以后有更多模型可比时再收紧。

---

## 5. 当前基线（2026-10-05，研究起点 2023-01-01，4h）

04 稳健性：

| case | 吃单：选择段 / 验证段中位数，两段都为正 | 挂单：同左 |
| --- | --- | --- |
| **`LgbmV2`**（基线） | **0.03 / 0.21，49%** | **1.06 / 1.29，90%** |
| `LgbmV1`（第一 / 第二版） | −2.83 / −1.20，0% | −1.61 / 0.29，5% |
| `直通·G0`（V1 + V2 等权） | −1.46 / 0.37，8% | −0.19 / 1.47，36% |
| 世坤线最好的 `L0 并集等权` | −0.98 / −0.59，5% | 0.43 / 0.82，56% |

V2 的 06 / 05（全部组合的中位数）：

- 赚钱季度占比 0.55（最高 0.73）；
- 风格归因：`beta[low_vol]` 0.23（选择段）/ 0.42（验证段），`beta[reversal]` 0.06 / 0.16，`beta[btc]` ≈ 0.02 / 0.12，`r2` 0.12 / 0.23；
- **`alpha_sharpe` 只有 0.22 / 0.13**：吃单下，剥离风格后的选币能力很弱，相当一部分收益是低波动风格。

结论：V2 是目前唯一"吃单下两段中位数不为负、挂单下稳健赚钱"的打分，可以作为基线；但它离"有选币能力的 alpha"还远。
下一步的改进（新特征、新模型）主要看能不能把 05 的 `alpha_sharpe` 和 04 的吃单中位数提上去。

---

## 6. 新想法的研究流程

```text
1. 筛选（快）：research/ml_training/run_experiments.py 里加 case，在探索工具里跟 h6_raw 系列比
   - 一次只改一件事（一组特征 / 一种损失 / 一种模型），多种子集成
   - 挑配置只看选择段，验证段只用来确认；看 summary.csv 的中位数和 both_pos_frac，不看最高格
2. 定型：把结论写成 models.py 里一个新的 MLAlpha 子类（spec + training_overrides）
3. 确认（正式）：MLalpha 研究线 run_training --force + run_track，按本文 §3 读 04 → 06 → 05 → 02，跟 §5 基线比
4. 全部定下来之后，holdout 只跑一次
```

---

## 7. 常见陷阱

| 陷阱 | 说明 |
| --- | --- |
| 看 RankIC 下结论 | RankIC 高 ≠ 赚钱（中位数效应）。看 04 和首尾价差 |
| 看网格最高的那一格 | 多重检验：39 个组合 × 多个 case，最高格天然偏乐观。看中位数和 `both_positive_frac` |
| 单个种子的结果 | 单个模型随机性很大（两组种子的打分截面相关只有 0.43–0.50），没做集成的结果不可信 |
| 宽 Top-K 在小币池里空仓 / 不平仓 | 早期每期只有 50–90 个币：top30 需要 60 个币才建仓、exit80 几乎从不触发平仓。优先看相对分位映射（`q*`）；04 已剔除空仓 > 20% 的组合 |
| 选择段偏乐观 | B 组世坤因子名单是在世坤研究线选择段上挑出来的 |
| 挂单假设 | `all_maker` 假设全部挂单成交、无逆向选择，是乐观上限；资金费率还没建模 |
| 只剥离 BTC | β_btc ≈ 0 只排除了押大盘方向，低波动 / 反转等风格要看 05 |
