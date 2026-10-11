# MLalpha：探索实验的 case 和正式工作流的 case（以及两者怎么对齐）

> 2026-10-10 写。读这份文档能回答：探索脚本里每个 case 改了什么、正式工作流里"case"是什么、一个探索结论要满足什么条件才能
> 原样搬进正式工作流。结果怎么读见 [`RESULT_READING.md`](RESULT_READING.md)。

---

## 0. 一句话

**探索和关卡3 只差第一层。**

| | 第一层：模型（用什么参数配置训练、产出一张 (T, N) 打分表） | 第二层：交易组合（同一张打分 → 39 个组合 × 4 种成本 × 2 段） |
| --- | --- | --- |
| **探索** | **变**：用各种参数配置出各种变体模型，每个模型各出一张打分 | 对每个模型的打分做多种交易组合检测 |
| **关卡3** | **固定**：模型写死在 `models.py` 的类里，只推断一次 | 对这一个（或一组）固定模型的打分做多种交易组合检测 |

第二层两边完全相同（见 §0.2、§3）。所以：**探索负责找模型（变第一层），关卡3 负责给选定的模型做最终鉴定
（只做第二层）**，两边看的是同一套 04 / 05 / 06 指标。

- **探索**（`research/ml_training/run_experiments.py`）：一个 case = **一套模型配置**（特征、标签、训练窗口、种子……），
  训练 → 样本外打分 → 用跟关卡3 相同的网格回测。用来快速比较"改一个东西有没有用"。
- **正式工作流**（`research/alpha_research/MLalpha/run_track.sh`）：模型配置写死在 `sherpa/alpha/custom/ml/models.py` 的类里，
  关卡3 的一个 case = **一个打分配方**（MLalpha 里就是 `single:custom.ml_lgbm_vX`，也就是"直接用这个模型的打分"）。
- 两边的"case"不是一个层级：**探索的一个 case ≈ 正式工作流里的一个模型类**；正式工作流的 case 是在模型之上做组合（单因子 /
  等权 / 路由），MLalpha 现在只用单因子。

### 0.1 用词：case、组合、成本、段

| 词 | 指什么 | 个数（MLalpha 现在） | 在哪定义 |
| --- | --- | --- | --- |
| **case（正式工作流）** | 关卡3 的一个**打分配方**：用哪些 alpha、什么方向和权重合成一张打分表 | 1 个：`single:custom.ml_lgbm_v4` | 关卡2 交接文件 `handoff/synthesis.json`（透传时由 `factor_synthesis/passthrough.py` 生成） |
| **case（探索）** | 一个**模型变体**（特征、标签、窗口、种子……）或一份打分来源 | 每批若干个 | `run_experiments.py` 的 `CASES` |
| **组合** | 把**同一张打分表**变成仓位的一种方式 = 映射 × 调仓频率 | 13 × 3 = **39** | `friction_test/config.py` 的 `WEIGHTINGS` × `REBALANCE_EVERY`（探索 `evaluation.py` 是它的拷贝） |
| **成本** | 同一条毛收益曲线按不同费率扣费，不改变交易路径 | 4 种（zero / all_maker / all_taker / stress） | 同上 `COST_MODELS` |
| **段** | 同一条连续净收益曲线按日期切开分别统计 | 2 段（选择 / 验证） | `research_config.json` 的 `validation_start` |

04 表一行 = 一个 case × 一种成本，行里选择段、验证段各一个中位数（一个 case 共 4 × 2 = 8 个中位数）；`n_combos` = 计入的组合数
（39 个去掉选择段空仓 > 20% 的）；中位数是对这些**组合**取的，成本和段不混在一起取。
05 / 06 表一行 = 一个 case × 一个组合（× 段）。

### 0.2 两层变数：正式工作流 vs 探索

一个结果由两层决定：**模型层**产出一张 (T, N) 打分表；**执行层**把这张表变成交易。

| | 第一层：模型（产出打分） | 第二层：执行（同一张打分 → 39 个组合 × 4 种成本 × 2 段） |
| --- | --- | --- |
| **正式工作流** | **固定**：配置写死在 `models.py` 的模型类里，步骤 0 按每 20 天一个重训时点训练、冻结成文件；关卡3 只推断（`registry.get(name)()` → `MLAlpha.compute`，`run_friction.py:195-197`），整个关卡3 只算这一张打分表 | 关卡3 展开：`run_friction.py:177` 建网格，`:319-327` 逐个组合回测、按成本扣费、分段统计，`:243` 取中位数 |
| **探索实验** | **在变**：每个 case 一个模型变体，各自训练、各自出一张打分表 | 跟关卡3 **完全相同**的展开（同一套网格、成本、空仓过滤、风格因子、季度统计） |

关卡3 的流程（以 V4 为例）：

```text
handoff/synthesis.json 里的配方 single:custom.ml_lgbm_v4
  └─ registry.get("custom.ml_lgbm_v4")() = LgbmV4()            模型类，配置是类属性
       └─ .compute(panel)：读 models/lgbm_v4/manifest.json，每个重训时点 18 个模型推断取平均 → (T, N) 打分
            └─ 套流动性掩码 → 逐期截面排名 → 按配方合成（单因子 = 它自己）              ← 到这里打分就定死了
                 └─ 39 个组合：同一张打分，不同的"选几个币、迟滞多宽、几根调一次仓"
                      └─ 每个组合一条毛收益曲线 × 4 种成本扣费 × 2 段 → 各自的 Sharpe
                           └─ 对 39 个组合取中位数 → 04 表
```

所以 39 个组合之间**打分完全相同**，不同的只是对打分的"解读"（选几个、什么时候平仓）和"执行"（调仓频率、成本）；
取中位数是为了评估"这个模型的打分换一种合理的交易方式还赚不赚钱"，而不是挑运气最好的一种。

探索比关卡3 **多一层变数**：先换模型（第一层），再对每个模型做同样的执行展开（第二层）。两边能比的前提是：

- **第二层两边完全一样**（网格、成本、过滤、汇总口径）——由 `tests/research/test_exploration_alignment.py` 守住；
- **第一层同一个配置两边训练出同一个模型**——`model_case` 取同一份配置，`data_random_seed` 固定后训练跟种子顺序无关。

满足这两条，探索里两个模型变体之间的差距，搬到正式工作流上才有意义。

---

## 1. 探索实验的 case

### 1.1 代码位置

| 东西 | 位置 |
| --- | --- |
| case 的定义（字段和默认值） | `research/ml_training/run_experiments.py` 的 `Case` dataclass |
| 全部 case 列表 | 同文件的 `CASES`（按批次排列，每批前有注释说明目的和结论） |
| 绑定正式模型的 case | 同文件的 `model_case(name, note, "LgbmV4")` |
| 训练 | 同文件 `train_case`，调 `dataset.build_training_frame` / `plan_folds` / `trainer.train_fold`——**跟正式训练 `run_training.py` 同一套函数** |
| 评估 | 同文件 `evaluate_case` + `research/ml_training/evaluation.py`（网格 / 成本是关卡3 的拷贝，单测保证一致） |
| 产出 | `research/alpha_research/MLalpha/experiments/<case>/`，汇总 `experiments/summary.csv` |
| 结论文档 | `experiments/FINDINGS.md`（第 1–5 批）、`FINDINGS_DERIVATIVES.md`（第 6 批）、`FINDINGS_V4.md`（第 7 批） |

跑法：`python research/ml_training/run_experiments.py --cases a,b`；`--reeval` 只重新评估已有打分；`--summary-only` 只重新汇总。

### 1.2 Case 的字段：改什么、什么意思、怎么影响结果

没写的字段 = 默认值。**注意默认值是 LgbmV1 第二轮（2026-10-05）的配置**，不是 V4：持有 1 根、排名标签、滑动 60 天、3 个种子、含 B 组。
所以早期 case 只写了改动项，后面的批次用 `V2` / `W4` 这类字典一次改一组（见 1.3）。

| 字段 | 默认 | 含义 | 对结果的影响（已有实验的结论） |
| --- | --- | --- | --- |
| `source` | `"train"` | 打分从哪来。`train` = 本脚本滚动训练；`official:<类名>` = 读正式模型（`MLAlpha.compute`）；`factor:<名字>` = 不用 ML，单个原始特征直接当打分；`blend:a+b` = 几个 case 打分的平均 | `blend` 用来凑更多种子；`factor` 是"ML 有没有比单因子强"的对照 |
| `horizon` | 1 | 训练标签持有几根 bar（t+1 → t+1+h 的收益） | **1 天（6 根）最好**：4 小时换手太高，12 小时 / 2 天更差 |
| `label_transform` | `"rank"` | 标签形态。`rank` = 截面排名；`raw_clip` = 原始收益 1%/99% 截尾 | **原始收益决定性地更好**：排名标签奖励"排名靠前"（中位数效应），Top-K 等权赚的是平均收益 |
| `objective` | `"ic_ir"` | 损失。`ic_ir` = −IC_IR（逐期加权相关）；`l2_rank` = 普通 MSE 回归 | MSE 明显更差 |
| `tail_quantile` / `tail_weight` | 0.2 / 3.0 | 标签排名首尾 20% 的行在损失里权重 ×3 | 去掉（`tail_weight=1`）不稳定，选择段好、验证段差 |
| `window_bars` | 360（60 天） | 训练窗口。数字 = 滑动窗口长度；`None` = 扩展窗口（从研究起点一直用到现在） | 扩展 ≥ 滑动 60 天 > 滑动 180 天，但扩展慢约 6 倍 |
| `valid_bars` | 120（20 天） | 早停用的内部验证段长度（窗口最后 20 天） | 没单独试 |
| `neutralize_label` | False | 标签先对 Beta / Size 截面回归取残差 | 更差 |
| `drop_features` | () | 按前缀去掉特征，`("alpha:",)` = 不要 B 组、`("market:",)` = 不要 C 组 | 有 B 组时去掉 B 很伤（第 5 批）；去掉 C 选择段变差 |
| `with_b` | True | False = 不算 B 组（世坤 13 个），比 drop_features 省计算 | V4 窗口下去掉 B 几乎无代价（第 7 批） |
| `extras` | () | A 组可选特征（`features.EXTRA_SYMBOL_FEATURES` 的名字）：多空比 4（`DERIVATIVES_LS`）、OI 2（`DERIVATIVES_OI`）、价量补充 4（`PRICE_VOLUME_EXTRAS`） | 见第 6、7 批；**特征组之间交互不稳定**（OI 有 B 时拖累、无 B 时有用） |
| `min_percentile` | 0.5 | 流动性范围：滚动成交额排截面前多少（特征排名、损失、评估都用这一份） | 收窄到前 40% / 30% 没有稳定改善，早期还经常空仓 |
| `research_start` / `validation_start` / `min_train_bars` | `research_config.json` / 180 天 | 研究窗口：取数起点（= 训练数据起点）、选择 / 验证分界、第一个模型最少攒多少数据 | 起点挪到 2024 会让头 10 个月训练历史太短（第 7 批） |
| `seeds` | (0,1,2) | 每个重训时点训练几个随机种子，打分取平均 | **影响非常大**：单个模型只有 1–几十棵树，换一组种子选择段中位数能差 0.4–1.0 |
| `lgb_overrides` | () | 覆盖 `config.LGB_PARAMS` 的个别项 | — |
| `model` | None | `model_case` 填的正式模型类名：特征清单直接用它的 `spec` | 用来保证"探索的就是正式要跑的那个模型" |
| `neutralize_scores` | () | 打分出来后剥离 vol42 / beta / size 暴露再交易（只对 `official` 打分用过） | 更差：V1 第二轮的边际大部分就是低波动 |

训练节奏（每 20 天重训一次、`num_boost_round=500`、早停 50 轮、`min_period_rows`）不在 Case 里，统一用 `config.py`；
`model_case` 会检查正式模型没改过这些，改了就报错。

### 1.3 全部批次

| 批 | case | 研究窗口 | 变了什么 | 结论 / 用途 |
| --- | --- | --- | --- | --- |
| 1 | `v2_official`、`v2_retrain` | 2022 起 | 正式模型打分 / 本脚本重训 | 核对探索跟正式一致（当时的 LgbmV1） |
| 1 | `h3` `h6` `h12` | 2022 | `horizon` | 持有期 |
| 1 | `h1_raw` `h6_raw` | 2022 | `label_transform="raw_clip"` | 原始收益标签更好 |
| 1 | `h6_win180` `h6_win365` `h6_expanding` | 2022 | `window_bars` | 训练窗口 |
| 1 | `h6_l2rank` `h6_notail` `h6_neutral` | 2022 | 损失 / 首尾加权 / 标签中性化 | 都不如默认 |
| 1 | `h6_noB` `h6_noC` `h6_p70` | 2022 | 去 B / 去 C / 收窄流动性 | 特征组和范围的消融 |
| 1 | `v2_resid_vol(_beta)` | 2022 | 正式打分剥离暴露 | 边际主要是低波动 |
| 2 | `f_*`（11 个） | 2022 | `source="factor:…"` | 单因子扣费后基本都亏 |
| 3 | `h6_raw_*`（12 个） | 2022 | 围绕"持有 1 天 + 原始收益"再扫一遍 | 找到盈利点 |
| 4 | `h6_raw_seed*`、`h6_raw_ens6/14` | 2022 | 换种子 / blend | 单模型随机性很大，必须集成 |
| 5 | `h6_raw_exp_*`、`h6_raw_exp_ens9` | 2022 | 扩展窗口 + 9 种子 | 成为 LgbmV2 |
| 6 | `d_base` `d_core` `d_oi` `d_ls` `d_wide` 及 `_s2`、`_ens18` | 2023 | V2 配置 + `extras`（OI / 多空比） | 多空比有用 → LgbmV3 |
| 7a | `w_v2` `w_v3` `v4_*` | **2024 起**（`W4`） | 去 B + 各组 extras | 2024 起点训练历史太短，选择段无区分度 |
| 7b | `v4h_*` 及 `_s2`、`_ens18` | 2023 | 去 B + 各组 extras | A+C+LS+OI+PV 最稳 → LgbmV4 |
| 8 | `m_v4`、`m_v4_official` | 2023 | `model_case("LgbmV4")` / 正式模型打分 | **一致性核对**：两者跟关卡3 逐格 / 逐位相同（§3.2） |

第 1–7 批的产出没有保留，case 定义留在代码里作记录，结论见 `experiments/FINDINGS*.md`（那些文档里的数字是早期评估口径，只看方向，不跟本文 / 关卡3 的数字直接比）。第 8 批起的产出跟关卡3 同口径。

### 1.4 每个 case 的产出（跟关卡3 同口径）

| 文件 | 内容 | 对应关卡3 |
| --- | --- | --- |
| `scores.pkl` | 样本外打分 (T, N) | — |
| `folds.csv` | 每个重训时点的早停轮数、内部验证 IC_IR | `ml_training/<模型>_folds.csv` |
| `friction_grid.csv` | 39 个组合 × 4 种成本 × 2 段的绩效 | `01_friction_summary.csv` |
| `robustness.csv` | 每种成本：两段中位数、为正占比、两段都为正 | `04_robustness.csv` |
| `style_attribution.csv` | 吃单净收益对 6 个风格回归（raw / alpha_sharpe、β） | `05_style_attribution.csv` |
| `quarterly.csv` | 吃单净收益分季度 | `06_quarterly.csv` |
| `diagnostics.csv` | RankIC、Pearson IC、首尾价差、vol 暴露（探索独有） | — |

`summary.csv` 每个 case 一行，列名对应：`taker_sel/val`、`taker_both_pos`（04 吃单）、`maker_*`、`gross_*`、`alpha_sel/val`（05）、
`pos_quarter_med`（06）……全部是**组合的中位数**，不挑最高格。

---

## 2. 正式工作流的 case

### 2.1 流程和代码

`bash research/alpha_research/MLalpha/run_track.sh`（编排在 `research/alpha_research/_pipeline/lib.sh`），按 `track.json` 跑：

| 步骤 | 代码 | 做什么 | 由什么决定 |
| --- | --- | --- | --- |
| 0 训练 | `research/ml_training/run_training.py` | 对 `track.json` 选中的每个 MLAlpha 子类滚动训练，模型写进 `models/<model_name>/` | 选哪些模型：`alphas.modules` + `alphas.include`；特征：模型类的 `spec`；训练配置：`config.py` 默认 + 模型类的 `training_overrides`；窗口：`research_config.json` |
| 1 阶段一 | `research/alpha_research/_pipeline/run_profile.py` | 每个 alpha 在**选择段**上算 IC 序列，按 regime（trend / volatility / dispersion / liquidity 各 3 个 state + 全局）切片 → `regime_alpha_profile_*.csv` | `regime.dimensions`、`preprocess`（掩码、是否中性化） |
| 2 汇总报告 | `research/regime_factor_report/` | 分类（Stable / Conditional …）、每个 state 的 Top 因子 → `results/report/` + 候选集 `handoff/report.json` | `report.min_abs_t`（2.0）、`report.matrix_top_k`（5） |
| 3 关卡1 | `research/factor_orthogonalization/` | 真跑：按 regime 算因子间截面相关、聚类去冗余；**MLalpha 透传**：候选集原样交下去 | `stages.orthogonalization.mode` |
| 4 关卡2 | `research/factor_synthesis/` | 真跑：G0 / L1 / L0 / L2 / L3 合成方案在验证段比较；**MLalpha 透传**：候选直接变成配方（`passthrough.py`） | `stages.synthesis.mode` / `passthrough` |
| 5 关卡3 | `research/friction_test/run_friction.py` | 每个配方 × 39 个组合 × 4 种成本回测 → `results/friction/00–06` | `friction_test/config.py`（网格、成本、红线） |

### 2.2 关卡3 里的"case"是什么

关卡3 的 case = 关卡2 交下来的一个**配方**（`handoff/synthesis.json`）。透传模式下可能有这几种（`factor_synthesis/passthrough.py`）：

| case 名 | 配方 | MLalpha 现在开不开 |
| --- | --- | --- |
| `single:<alpha>` | 只用这一个 alpha 的打分，方向 = 阶段一选择段 IC_IR 的符号 | **开**（`singles: true`） |
| `直通·G0 全局等权` | 全局候选名单方向对齐后等权 | 关（`equal_weight: false`，研究线只评估单个模型） |
| `直通·L0 并集等权` | 各 state 名单并集等权 | 关 |
| `直通·L2-<维度> 路由等权` | 当前 bar 在哪个 state 就用哪个 state 的名单 | 关（`routed: false`） |

只有一个模型时这几种本来也会退化成同一个配方（会被去重）。

每个 case 再展开成**组合**（这才是 04 表里"39 个"的来源，`friction_test/config.py`）：

| 维度 | 取值 | 含义 |
| --- | --- | --- |
| 映射（13 个） | `top10`、`top10_exit20/30/50`、`top20`、`top20_exit40/60/100`、`q10`、`q10_exit20/30`、`q20`、`q20_exit40` | `topK_exitE` = 做多打分最高的 K 个、做空最低的 K 个，跌出前 E 名才平仓（迟滞，降换手）；`qX_exitY` = 同理但按当期币数的比例（前 X% 开仓、跌出前 Y% 平仓），币池大小变了含义不变 |
| 调仓频率（3 个） | 1 / 3 / 6 根 bar | 每隔几根 bar 才允许调一次仓（1 = 每 4 小时、3 = 每 12 小时、6 = 每天），不调仓的 bar 不交易、持仓随价格漂移；越稀疏换手越低、信号越旧。**注意：这是调仓间隔，不是持有期**——一个币实际拿多久取决于它什么时候跌出平仓线（映射里的 exit），可能跨好几个调仓周期。也不要跟模型的 **horizon** 混淆：horizon 是训练标签的持有期（V4 是 6 根，`training_overrides["label_horizon_bars"]`），属于模型层，步骤 0 训练时就定了，关卡3 不碰它 |
| 成本（4 种） | `zero` / `all_maker`（2 bps）/ `all_taker`（5+3 bps，**主口径**）/ `stress`（5+10 bps） | 净收益 = 毛收益 − 换手 × 单边成本。成本不改变交易路径，只是对同一条毛收益曲线按不同费率扣费；它**不参与**取中位数，而是分开报告（见下） |
| 段（2 个） | 选择段（从第一根有打分的 bar 到 `validation_start`）/ 验证段 | 同一条连续持仓路径分开统计 |

04 表的中位数 = 一个 case 在某种成本下，这 39 个组合（去掉选择段空仓 > 20% 的）在某一段净 Sharpe 的中位数。

所以一个 case 一共有 **4 种成本 × 2 段 = 8 个中位数**，每个都只在 39 个组合上取——**不是**把 13 × 3 × 4 = 156 个结果混在一起取一个中位数。
成本档位不是"一种合理的交易方式"，而是对同一种交易方式的不同费率假设，混进去取中位数没有意义。主口径看 `all_taker` 那一行，
`zero` 看信号本身强不强，`all_maker` / `stress` 看对成本有多敏感。

一句话：**关卡3 = 1 个 case（固定模型的一张打分表）× 39 个组合（13 种"选几个、何时平仓" × 3 种调仓间隔），每个组合一条收益曲线；
再按 4 种成本分别扣费、按 2 段分别统计；每种成本、每个段各取一次 39 个组合的中位数。** 它测的是"同一个模型、同一张打分，换不同
执行方式还成不成立、扣掉成本还剩多少"；"哪个模型更好"不归关卡3 管，那是模型层（探索 / 换模型类后重跑）的事。

---

## 3. 探索 ↔ 正式：怎么对应

### 3.1 对应关系

| 环节 | 探索 | 正式 | 一致性 |
| --- | --- | --- | --- |
| 特征清单 | `Case.spec`（`model_case` 时 = 模型类的 spec） | 模型类的 `spec` | 用 `model_case` 时完全相同（指纹相同） |
| 训练配置 | Case 字段 | `config.for_model(training_overrides)` | `model_case` 用同一个函数取 |
| 训练函数 | `build_training_frame` / `plan_folds` / `train_fold` | 同 | 同一份代码 |
| 训练可复现 | 同一配置、同一组种子 → 同一批模型，跟种子分几组跑无关 | 同 | `config.LGB_PARAMS["data_random_seed"]` 固定（见 3.2） |
| 研究窗口 | Case 的 `research_start` 等（默认 = research_config） | `research_config.json` | 默认一致 |
| 多种子合成 | 一个 case 训多个种子取平均；`blend` 取原始预测平均 | `MLAlpha.compute` 取原始预测平均 | 一致 |
| 打分预处理 | 套流动性范围 → 截面排名 | 套 track 掩码（= 同一个范围，训练脚本校验）→ 截面排名 | 一致 |
| 方向 | 不翻转（模型训练目标就是正 IC） | 透传配方的方向 = 阶段一选择段 IC_IR 符号 | ML 模型 IC 恒为正，实际一致 |
| 组合网格 / 成本 / 空仓过滤 | `evaluation.py` | `friction_test/config.py` | 一致，单测 `tests/research/test_exploration_alignment.py` |
| 汇总指标 | `summary.csv` | 04 / 05 / 06 | 同口径、同函数 |
| 正式独有 | — | 阶段一 regime 体检、关卡1/2 | 对单模型 MLalpha 只是诊断 / 透传，不改变打分 |
| 探索独有 | `factor:` / `blend:` / `neutralize_scores`、`diagnostics.csv` | — | 只用于研究，不影响可比性 |

### 3.2 保证两边一致的关键设计，以及核对结果

1. **执行层只有一份定义**：探索的 `evaluation.py` 是关卡3 `friction_test/config.py` 的拷贝（research 子项目之间不互相 import），
   单测逐项比对网格、调仓频率、成本、空仓过滤；汇总表用同样的函数（`cost_segment_rows` / `attribute` / `period_stats`）。
2. **多种子合成 = 原始预测值平均**，跟 `MLAlpha.compute` 一样；两组 9 种子 blend 起来 = 同一批 18 个模型一起训练。
3. **训练集分箱随机数固定**（`config.LGB_PARAMS["data_random_seed"]`）：LightGBM 只在第一次训练时给训练集分箱，行数 > 20 万
   （`bin_construct_sample_cnt`）时要抽样；随机数不固定的话取自"第一个训练的种子"，同一个种子的模型就会因为前面先训了谁而不同
   （同一份训练集，种子 10 的早停轮数在"先训种子 0 / 9 / 10"时是 16 / 22 / 107）。固定后跟顺序无关，单测
   `test_a_seed_trains_the_same_model_regardless_of_which_seeds_ran_before_it` 守住。

**核对**（第 8 批）：正式 V4 跑完整研究线，同时在探索里跑 `m_v4`（`model_case("LgbmV4")`，本脚本训练）和 `m_v4_official`（读正式模型打分）：

| 核对项 | 结果 |
| --- | --- |
| 打分（815,172 个非空格子） | 格子完全一致，最大差 2.7e-11（浮点精度） |
| 04（4 种成本 × 2 段 × 6 列） | 关卡3 = `m_v4` = `m_v4_official`，逐位相同 |
| 05（78 行）/ 06（39 行） | 差 0.0 |

**随机波动量级**：同一个配置只换训练随机性（分箱 / 种子），关卡3 吃单中位数会动 ±0.15–0.2、两段都为正的占比会动约 5 个百分点。
比较两个模型时，差距小于这个的不要当真。

### 3.3 以后的规矩

1. 探索新想法照常写 Case；**一旦要进正式工作流，先写成 `models.py` 里的模型类，再用 `model_case` 在探索里跑一次**，
   确认结果后再跑 `run_track.sh`。两边的打分应该逐格相同、04 指标应该相同（第 8 批 `m_v4` / `m_v4_official` 就是这个核对）。
2. 比较两个配置时，**同一批、同一组种子、同一个研究窗口**才可比；FINDINGS 文档里早期批次的数字只看方向。
3. 种子噪声跟我们要判断的差距同一量级：结论至少要两组不重叠的种子都成立。
