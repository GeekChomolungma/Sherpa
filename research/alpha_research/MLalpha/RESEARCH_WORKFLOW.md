# MLalpha 研究工作流：一个新模型从想法到成为基线

> 给第一次做 MLalpha 研究的人：先读本文知道"按什么顺序做什么"，细节再按需查——概念（case、组合、两层）见
> [`CASES.md`](CASES.md)，结果怎么读见 [`RESULT_READING.md`](RESULT_READING.md)，训练这一步见
> [`../../ml_training/README.md`](../../ml_training/README.md)。当前基线是 **`LgbmV4`**（`RESULT_READING.md` §5）。

---

## 0. 先建立两个概念

**两层**：一个结果由两层决定。

| | 第一层：模型 | 第二层：交易组合 |
| --- | --- | --- |
| 是什么 | 用什么特征 / 标签 / 窗口 / 种子训练，产出一张 (T, N) 打分表 | 同一张打分 → 39 个组合（13 种"选几个、何时平仓" × 3 种调仓间隔）× 4 种成本 × 2 段 |
| 探索实验 | **变**：每个 case 一个模型变体 | 跟关卡3 完全相同 |
| 正式工作流（关卡3） | **固定**：写死在 `models/` 里的模型类上 | 同上 |

所以：**探索负责找模型，正式工作流负责给选定的模型做最终鉴定**，两边看同一套 04 / 05 / 06 指标，同一个配置两边结果逐位相同。

**两段**：研究段按 `research_config.json` 切成选择段（2023-01-01 ~ 2024-06-30）和验证段（2024-06-30 ~ 2026-03-15）。
**做决定只看选择段，验证段只用来确认**；holdout（2026-03-15 ~ 2026-09-15）全部定下来之后只跑一次。

---

## 1. 流程总览

```text
 想法
  │
  ▼
① 探索      research/ml_training/run_experiments.py      加 case，跟基线 m_v4 同批比较
  │            （赢了？两组种子都成立？）
  ▼
② 定型      sherpa/alpha/custom/ml/models/<家族>.py    写成新模型类（如 XgbV5）；探索里用 model_case 跑一次
  │
  ▼
③ 正式      run_track.sh --alphas custom.ml_xgb_v5        跑完整研究线，产出自动进 runs/xgb_v5/
  │            （结果跟 ② 逐位一致？）
  ▼
④ 归档      runs/<model_name>/ 已经按模型分开，不用复制改名；关键数字写进文档
  │
  ▼
⑤ 比基线    04 → 06 → 05 → 02，跟 RESULT_READING §5 的 V4 逐项比
  │            （各维度都赢？）
  ▼
⑥ 换基线    更新 RESULT_READING §5；全部定下来后 holdout 只跑一次
```

---

## 2. 每一步怎么做

### ① 探索：先在便宜的地方比

在 `research/ml_training/run_experiments.py` 的 `CASES` 里加 case（字段含义见 `CASES.md` §1.2），跟基线放在**同一批**：

```python
CASES += [
    model_case("m_v4", "基线", "LgbmV4"),                                   # 已有
    model_case("x_new_feat", "V4 + 某组新特征", "LgbmV4", extras=(...)),     # 在基线上只改一件事
    model_case("x_new_feat_s2", "同上换种子 18-35", "LgbmV4", extras=(...), seeds=tuple(range(18, 36))),
]
```

```bash
python research/ml_training/run_experiments.py --cases m_v4,x_new_feat,x_new_feat_s2
```

看 `experiments/summary.csv`（列跟关卡3 的 04 / 05 / 06 一一对应）。判断规则：

- **一次只改一件事**（一组特征 / 一种损失 / 一个训练参数）；
- **同批、同种子组、同研究窗口**才可比；
- **只用选择段挑**（`taker_sel`），验证段（`taker_val`）只确认；看中位数和 `taker_both_pos`，不看最高格；`alpha_sel` / `alpha_val`
  （05 剥离风格后的 Sharpe）只看收益来源，不参与挑选（`RESULT_READING.md` §3 第 3 步）；
- **差距小于 ±0.15–0.2 不算赢**（同配置只换训练随机性就会动这么多），结论要两组不重叠的种子都成立。

新特征先写进 `sherpa/alpha/custom/ml/features.py` 的 `EXTRA_SYMBOL_FEATURES`（可选项，默认不带，不影响已有模型的指纹），要有
point-in-time 单测。

### ② 定型：写成模型类

在 `sherpa/alpha/custom/ml/models/` 下对应家族的文件里加一个 `MLAlpha` 子类（照 `models/lgbm.py` 的 `LgbmV4` 抄；新家族新建一个文件，在 `models/__init__.py` 里 import）：`name` / `model_name` / `spec`（特征清单、流动性范围）/
`training_overrides`（训练配置，含模型架构 `backend`：`lightgbm` / `xgboost` / `lstm`，见 `research/ml_training/README.md` §8.1）。
**配置只写在类属性上**——正式工作流按名字无参实例化它。只换架构、不换特征时 `spec` 直接复用 `LgbmV4.spec`，`model_name` 换一个新的。

然后在探索里用 `model_case("m_v5", "...", "LgbmV5")` 再跑一次。这个 case 跟正式工作流里的 V5 是同一个模型。

### ③ 正式工作流：纯模式跑完整研究线

```bash
# --alphas 指定这次只评估新模型（关卡2 只透传单因子），不用改 track.json；不写 = track.json 的 include（当前基线 V4）
bash research/alpha_research/MLalpha/run_track.sh --alphas custom.ml_xgb_v5 --dry-run    # 先看要跑哪些步骤、产出去哪
CH_HOST=... CH_PASSWORD=... bash research/alpha_research/MLalpha/run_track.sh --alphas custom.ml_xgb_v5
```

不同模型的 run 互不覆盖，可以开几个终端同时跑（比如 XGBoost 和 LSTM 各一个）。

依次跑：步骤 0 训练（`models/xgb_v5/`）→ 阶段一 Regime 体检 → 汇总报告 → 关卡1 / 2 透传 → 关卡3 扣费回测。约 40–50 分钟（18 种子）。

**核对**：关卡3 的 `04_robustness.csv` 应该跟 ② 里 `m_v5` 的 `robustness.csv` 逐位相同。对不上说明某个环节口径不一致，先查清楚再往下走。

### ④ 归档

2026-10-24 起不用手动归档：MLalpha 研究线按 run 归档（`track.json` 的 `outputs.per_run`），每次运行的三样产出直接写进
`runs/<run_id>/`，`run_id` = 参评模型的 `model_name`：

```text
MLalpha/
  models/<model_name>/                       模型文件（不进 git，manifest.json 进）
  runs/<run_id>/                             一次正式运行的全部产出
    regime_alpha_profile_without_neutralization.csv    阶段一长表
    handoff_without_neutralization/                    report / orthogonalization / synthesis.json
    results_without_neutralization/                    ml_training/ report/ friction/
  comparisons/<主题>/                        跨 run 的横比文档（v1_v4、v4_start）
  experiments/<case>/                        探索实验（本来就按 case 分开）
```

| run 名 | 含义 | 怎么跑出来 |
| --- | --- | --- |
| `lgbm_v4`（当前基线）、`lgbm_v1` … | 模型纯模式、默认研究窗口 | `--alphas custom.ml_lgbm_v4`（或不写，用 track.json 的 include） |
| `<model_name>__<变体>`（如 `lgbm_v4__start2024`） | 非默认设置的变体（比如临时改了研究起点），后缀写明改了什么 | 再加 `--variant start2024`；模型文件也自动进 `models/lgbm_v4__start2024/`，不会覆盖正式模型 |
| `a+b` | 一次评估多个模型（关卡2 透传出的等权等配方） | `--alphas custom.ml_a,custom.ml_b` |

哪个 run 是基线写在 `RESULT_READING.md` §5，不再靠"不带后缀的目录"表示。git 里只提交其中的 md / json 和 `manifest.json`；
04–06 的 CSV、模型文件只留本地，关键数字写进文档。

### ⑤ 跟基线比

按 `RESULT_READING.md` §3 的顺序读，跟 §5 的 V4 逐项比：

| 顺序 | 表 | 看什么 | V4 基线（吃单，选 / 验） |
| --- | --- | --- | --- |
| 1 | `04_robustness.csv` | 吃单两段中位数、两段都为正 | 0.88 / 0.49，69% |
| 2 | `06_quarterly.csv` | 赚钱季度占比 | 0.64 |
| 3 | `05_style_attribution.csv` | **诊断，不判输赢**：剥离风格后的 alpha_sharpe、各风格 β，看收益来源有没有变 | 0.98 / 0.63；β[低波动] 0.17 / 0.38 |
| 4 | `02_validation_base_cost.csv` | 具体组合、换手、保本成本 | 换手 0.15 / 根，保本 13.0 bps |

### ⑥ 换基线 / holdout

04 / 06 / 02 各项都赢（且超过随机波动）才换基线，05 不参与判定：更新 `RESULT_READING.md` §5（基线指向新模型的 `runs/<model_name>/`），`track.json` 的 `alphas.include` 改成新模型（不写 `--alphas` 时默认跑基线）。关卡3 红线（吃单验证段净 Sharpe ≥ 2.5、
换手衰减 < 40%）是"能不能进下一阶段"的门槛，目前没有模型过。研究结论全部定下来之后，holdout 只跑一次。

---

## 3. 常见坑

| 坑 | 正确做法 |
| --- | --- |
| 跨批次比较探索数字 | 只在同批、同种子组、同窗口内比；`experiments/FINDINGS*.md` 里早期批次的数字只看方向 |
| 只跑一组种子就下结论 | 至少两组不重叠的种子 |
| 看网格里最高的那一格 | 看 39 个组合的中位数和两段都为正 |
| 用验证段挑配置 | 选择段挑，验证段确认 |
| 探索里手写一份"差不多"的配置去代表正式模型 | 用 `model_case` 绑定模型类 |
| 研究起点往后挪来"避开币少的年份" | 起点就是训练数据起点，挪了会让模型训练历史变短、两段都变差（`results_v4_start_comparison/`）；嫌早期币少只在评估时单看后段 |
| 改了 `evaluation.py` 的网格 / 成本 | 它是关卡3 `friction_test/config.py` 的拷贝，两边一起改，单测会拦 |
| 改了 `ml_training/config.py` 或模型的 `training_overrides` | 配置指纹变了，已有模型不能续训，要 `run_training.py --force` 重训 |

---

## 4. 不是 ML 模型的新想法

不需要训练的策略 / 因子（比如"骑 beta"这类规则）不走本文的 ① ② 和步骤 0：写成普通 alpha（`sherpa/alpha/custom/` 下注册），放进一条
自定义研究线（`research/alpha_research/<track>/`，参考 `custom_starter/`），直接跑阶段一 → 关卡3。关卡3 的网格、成本、04 / 05 / 06 口径
跟 MLalpha 完全相同，所以结果仍然可以直接跟 V4 基线比。
