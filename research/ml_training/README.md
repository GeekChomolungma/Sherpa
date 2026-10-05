# ML Training：ML alpha 研究线的步骤 0（滚动训练）

> **状态：第一版已落地**（`run_training.py`，LightGBM + IC_IR 损失）。设计和决策记录见
> [`sherpa/alpha/custom/ML_ALPHA_DESIGN.md`](../../sherpa/alpha/custom/ML_ALPHA_DESIGN.md)；本文只讲训练这一步怎么跑、
> 每一步做了什么、产出在哪。训练完之后结果怎么读、新模型怎么跟基线 `LgbmV2` 比，见
> [`research/alpha_research/MLalpha/RESULT_READING.md`](../alpha_research/MLalpha/RESULT_READING.md)。

---

## 1. 这一步在流水线里的位置

ML alpha 和其它 alpha 的唯一区别，是**多了一个训练步骤**。之后的阶段一 → 汇总报告 → 关卡1/2/3 完全照搬，每个阶段的
输入输出接口不变：

```text
步骤 0  滚动训练（本目录）  ──>  模型文件 + 模型清单（磁盘）
                                        │
步骤 1~5  现有流水线  ──  registry.get("custom.ml_lgbm_v1")().compute(panel)  ──  (T, N) 打分
                                        │
                     MLAlpha.compute() 读模型清单，每一行用负责它的模型推断
```

两半之间只靠磁盘上的文件交接：

- **训练**（本目录）：只在离线跑，可以依赖 lightgbm；把模型训练好、冻结成文件，写进模型清单；
- **推断**（`sherpa/alpha/custom/ml/`）：`MLAlpha.compute()` 只推断、不训练。研究流水线（以后实盘也一样）把它当普通
  alpha 用，完全不知道背后是模型。

所以"打分怎么算"完全由 ML alpha 自己决定，流水线这边什么都不用改。

---

## 2. 入口

```bash
# 整条研究线（步骤 0 训练 + 步骤 1~5 评估）
bash research/alpha_research/MLalpha/run_track.sh

# 只训练
python research/ml_training/run_training.py --track MLalpha
python research/ml_training/run_training.py --track MLalpha --force   # 特征或配置变了，删掉旧模型全部重训

# 模型已经训练好，只做评估
bash research/alpha_research/MLalpha/run_track.sh --from-step 1
```

需要 ClickHouse 环境变量（`CH_HOST` 必填，见其它关卡）和 ML 依赖（`pip install -e .[ml]`，即 lightgbm）。

---

## 3. 一次训练做了什么

入口是 `run_training.py` 的 `main()`，按顺序做 6 件事。括号里是 2026-10-01 第一次真实运行的数字。

### ① 找出要训练哪个模型

读研究线的 `track.json`（`alphas.modules = sherpa.alpha.custom.ml.models`），挑出其中的 `MLAlpha` 子类，目前只有
`LgbmV1`（`custom.ml_lgbm_v1`）。这个类上用类属性写死了两件事：

- `spec`：用哪些特征（`FeatureSpec`，见 ④）；
- `model_name`：模型文件放在 `research/alpha_research/MLalpha/models/<model_name>/`。

研究流水线按名字无参创建 alpha，所以模型配置只能写在类属性上，不能靠构造参数。想换特征或另起一个模型，就在
`models.py` 里再注册一个子类。

### ② 取数

`data.py`：从 ClickHouse 取 `research_start ~ research_end`（2022-01-01 ~ 2026-03-15）的 4h 全市场 K 线。
`--until holdout` 会取到 `holdout_end`，让模型覆盖 holdout 段——研究结论定下来之前不要用。

### ③ 流动性范围（损失掩码）：只有一个来源，`spec.liquidity`

流动性范围写在模型的 `FeatureSpec.liquidity` 上（`models.py`，`LiquidityFilter`，门槛参数同 `tradable_mask`）。LgbmV1
设成：滚动 120 根成交额中位数排在截面前一半、不设绝对地板、上线满 20 根。流动性差的币做 Last-K 实际成交不了，不该
影响模型。这一份范围在三处共用：

| 用在哪 | 作用 |
| --- | --- |
| 特征（`build_features`） | A、B 组的截面排名只在范围内做：时序部分先在全量数据上算完，再盖掉范围外，最后排名——范围逐期变化，先盖再 rolling 会把进进出出的币的时序打断 |
| 训练（`build_training_frame`） | 标签只在范围内有值，范围外的行不进训练集，也不参与损失 |
| 推断（`MLAlpha.compute`） | 范围外的格子不打分（NaN） |

研究流水线评估时（阶段一 ~ 关卡3）用的外层掩码来自研究线 `track.json` 的 `preprocess.tradable_mask`，是另一处配置。
训练脚本开头会把它补全 `tradable_mask` 的默认值、换算成 `LiquidityFilter`，跟每个模型的 `spec.liquidity` 比较，
不一致直接报错（`run_training._check_liquidity`）。MLalpha 研究线对应写成
`{"min_percentile": 0.5, "min_quote_volume": 0, "min_trades_count": 0}`。

### ④ 构建训练集（`dataset.py` 的 `build_training_frame`）

对整段面板**一次算好**，之后每个重训时点只按时间切片：

| 部分 | 内容 | 实现 |
| --- | --- | --- |
| 特征 | 每个 (时间, 币) 一行，33 列（2026-10-02 去冗余后；第一次运行时是 36 列）。A 组 11 个量价衍生量 + Beta（每期在流动性范围内截面排名，每块的含义见 `features.py` 里 `SYMBOL_FEATURES` 的注释框）；B 组 13 个世坤因子打分（每期截面排名）；C 组 8 个市场状态量（广度、波动率分位数……，同一期所有币相同） | `sherpa/alpha/custom/ml/features.py`，训练和推断共用这一份 |
| 标签 | 这个币 `t+1 → t+2` 的收益（`research_config.json` 的持有 1 根、延迟 1 根，跟阶段一的 IC 标签同一口径），套损失掩码，可选中性化（`NEUTRALIZE_LABEL`，默认关），再做截面排名 | `dataset.build_labels` |
| 权重 | 标签排名在首尾各 20% 的行权重 3，其余 1 | `objective.tail_weights` |

只保留掩码内、标签已知的行，按时间排好序（93 万行，构建 39 秒）。

### ⑤ 滚动训练（`run_training.train_alpha`）

`dataset.plan_folds` 先排出时间表：第一个重训时点 τ₁ = 研究起点 + 180 天（2022-06-30），之后每 20 天一个（共 68 个）。
时间表只由研究起点和参数决定，跟数据取到哪天无关，所以数据变长后再跑，前面的重训时点不变。

对每个重训时点 τ（2026-10-05 起：滑动窗口 + 两步训练）：

```text
训练窗口：τ − 60 天 ~ τ − 2 根 bar（滑动：每 20 天整体往前挪，更早的数据不再使用）
          （purge：标签用到 t+2 根的收盘价，所以只有 t <= τ−2 的行，在 τ 时刻标签已经知道）

每个随机种子两步：
① 早停：  [──── 拟合段（约 40 天）────]  隔 2 根  [── 内部验证段：窗口里最近 20 天 ──]
          在拟合段上长树，验证段上 IC_IR 连续 50 轮不刷新最好成绩就停 → 最佳轮数 k
② 重训：  [──────────── 整个训练窗口 60 天（拟合段 + 间隔 + 验证段）────────────]
          按 k 轮重新训练，不再早停 → 保存这一步的模型
          验证段只负责回答"训练几棵树"，答完也参与长树：模型学到的数据一直到 τ − 2 根 bar，不会隔着验证段去预测

3 个随机种子 → 3 个模型文件：models/lgbm_v1/<τ>/seed{0,1,2}.txt
清单里追加一条：这个模型负责 [τ, τ + 20 天)
```

为什么验证段固定 20 天而不按比例切：按比例切时，扩展窗口越长验证段越长（第一版最后几个重训时点是 7 个月），这一段
只用来早停、不长树，模型学到的数据比 τ 早好几个月。早停选出来的轮数本身噪声很大（单期 IC 标准差约 0.16，20 天
120 期的标准误约 0.015，跟轮数之间的 IC 差别同一量级），所以第②步重训比"早停选得多准"更重要。

- **损失**（`objective.py`）：−IC_IR。每期 IC 是预测值和标签的加权 Pearson 相关（标签已经是排名，所以接近 RankIC，
  但处处可导）；首尾权重见 ④。梯度是解析式（单测用数值差分核对过），二阶导取常数 1、梯度按均方根归一。
  `config.OBJECTIVE = "l2_rank"` 可以换成"排名标签上的加权 MSE"作对照；
- **训练循环**（`trainer.train_fold`）：LightGBM，每个种子两步——拟合段上早停找轮数，整个窗口按轮数重训；
- **增量**：清单里已有、模型文件齐全的重训时点直接跳过；每训完一个就写一次清单，中途打断下次从断点续上；
- **配置保护**：清单里记着特征清单和训练配置的指纹。改了 `config.py` 或特征，再跑会拒绝续训（不会悄悄混用两套
  配置的模型），确认要重训就加 `--force`；
- **自检**：每个重训时点都检查训练行没有越过 τ − 2 根 bar，越过就直接报错。

（第一版是扩展窗口、按 15% 切验证段、不重训：68 个重训时点 × 3 个种子，训练用时 5.5 分钟。）

### ⑥ 样本外自检（`run_training.evaluate`）

每个模型只预测它负责的那 20 天，拼成一条全程样本外的打分，在损失掩码内逐期算 RankIC，写进
`<研究线>/results*/ml_training/`。这一步的数字和后面阶段一算出来的应该一致（第一次运行：选择段 IC_IR 都是 0.27）。

---

## 4. 训练代码架构：从 `main()` 读起

整个训练流程的主线就是 `run_training.py` 的 `main()`，其它文件都是它调用的细节：

```text
main()                                        run_training.py
 ├─ load_track / _ml_alphas                   读 track.json，找到要训练的 MLAlpha 子类（LgbmV1）
 ├─ load_universe_panel                       data.py：取数
 ├─ _check_liquidity                         校验模型 spec.liquidity 跟 track.json 的评估掩码一致
 ├─ build_training_frame                      dataset.py            ← 数据怎么来
 │    ├─ spec.liquidity.mask                  流动性范围（特征排名和标签共用）
 │    ├─ build_features                       sherpa/alpha/custom/ml/features.py（特征公式在 SYMBOL_FEATURES / MARKET_FEATURES）
 │    ├─ build_labels                         dataset.py：未来收益 → 掩码 → （可选中性化）→ 截面排名
 │    └─ tail_weights                         objective.py：首尾加权
 ├─ train_alpha                               run_training.py       ← 怎么按时间切、怎么续训
 │    ├─ _prepare_manifest                    读旧清单，校验特征 / 配置指纹（不一致就拒绝，--force 才重训）
 │    ├─ plan_folds                           dataset.py：重训时点时间表
 │    └─ 每个还没训练的重训时点：
 │         rows_between                       dataset.py：取 τ − 2 根 bar 及以前的训练行（purge）
 │         split_inner_validation             dataset.py：拟合段 / 内部验证段（最近 20 天），中间隔 2 根 bar
 │         train_fold                         trainer.py：每个种子 ① 拟合段上 lgb.train + 早停 → 轮数 k
 │                                                        ② 整个窗口 lgb.train k 轮 → 存模型文件（损失 = objective.ICIRObjective）
 │         save_manifest                      sherpa/alpha/custom/ml/manifest.py：追加一条，立即落盘
 └─ evaluate                                  run_training.py：每个模型预测它负责的 20 天 → 逐期 RankIC → 写 CSV
```

建议的读法：

1. 先通读 `main()`（约 45 行），知道整体流程；
2. 再看 `build_training_frame` 和 `train_alpha`：数据怎么来、怎么按时间切，都在这两个函数里；
3. 对损失的数学定义有疑问时再看 `objective.py`（开头注释写了公式）；梯度的正确性由
   `test_ic_ir_gradient_matches_finite_differences` 保证，不用自己推。

各文件的职责：

| 文件 | 职责 | 依赖 |
| --- | --- | --- |
| `run_training.py` | 编排：上面的整棵调用树、增量 / 指纹 / 报告 | 下面全部 |
| `config.py` | 所有训练参数（§8） | 无 |
| `data.py` | 取数 | ClickHouse |
| `dataset.py` | 标签、训练集、时间表、内部验证切分 | `features.py`、`objective.py` |
| `objective.py` | IC_IR 损失和梯度、首尾权重 | 只有 numpy |
| `trainer.py` | 单个重训时点的训练、逐期 RankIC | lightgbm |

`dataset.py` / `objective.py` / `trainer.py` 都是纯函数，不连数据库、不读写清单，单测直接喂合成面板。

---

## 5. 训练结果：保存了什么

都在 `research/alpha_research/MLalpha/` 下，分三类。

### 5.1 模型文件（不进 git）

```text
models/lgbm_v1/20240709T0000/seed0.txt
                             seed1.txt
                             seed2.txt
```

- 每个重训时点一个子目录（目录名 = 它开始负责的时间），每个随机种子一个文件。第一次运行 68 × 3 个文件，共 4.3MB；
- LightGBM 的纯文本模型：树的结构（分裂特征、阈值、叶子值）和特征名。只存到早停时的最佳轮数（比如这个时点三个种子
  分别是 10、3、1 棵树）；
- 模型文件里的特征名把冒号等特殊字符换成了下划线（`alpha:worldquant.alpha040` → `alpha_worldquant_alpha040`），
  LightGBM 不允许。推断时按**列的位置**喂数据，名字只是记录用。

### 5.2 模型清单 `models/lgbm_v1/manifest.json`（进 git）

文件头记录"这批模型是怎么训练出来的"：

| 字段 | 内容 |
| --- | --- |
| `model` | 模型名（= 目录名） |
| `feature_fingerprint` / `feature_names` | 特征清单的指纹和全部特征名（顺序就是推断时喂给模型的列顺序） |
| `config_fingerprint` / `config` | 训练配置的指纹和全文：`config.py` 的全部参数 + 时间口径（周期、研究起点、持有期、执行延迟）+ 大盘锚点。流动性范围在 `spec.liquidity` 里，进的是特征指纹 |
| `entries` | 每个重训时点一条，见下 |

一条 `entries`（第一次运行的真实内容）：

```json
{
  "valid_from": "2024-07-09T00:00:00Z",        // 这个模型负责 [valid_from, valid_until)
  "valid_until": "2024-07-29T00:00:00Z",
  "train_rows_until": "2024-07-08T16:00:00Z",  // 训练行截止（τ 减 2 根 bar）
  "files": ["20240709T0000/seed0.txt", "20240709T0000/seed1.txt", "20240709T0000/seed2.txt"],
  "n_train_rows": 280204,                      // 拟合段行数（不含内部验证段）
  "n_inner_valid_rows": 81040,
  "best_iterations": [10, 3, 1],               // 各种子早停时的树数
  "metrics": {"inner_valid_ic_ir_by_seed": [0.208, 0.251, 0.237]}
}
```

两个指纹的作用：

- **推断时**：代码里的特征清单（`FeatureSpec.fingerprint`）和清单里的 `feature_fingerprint` 对不上，`MLAlpha` 直接报错，
  不会拿新特征喂旧模型；
- **训练时**：特征或配置变了，`run_training.py` 拒绝在旧清单上续训，加 `--force` 才删掉旧模型全部重训。

清单先写临时文件再替换，训练中途被打断也不会留下半截文件。

### 5.3 训练报告（CSV，不进 git）

`<研究线>/results*/ml_training/` 下（MLalpha 研究线 `neutralize: false`，所以是 `results_without_neutralization/`）：

| 文件 | 内容 |
| --- | --- |
| `<model_name>_folds.csv` | 每个重训时点一行：训练行数、早停轮数、内部验证 IC_IR、它负责那 20 天的样本外 RankIC |
| `<model_name>_oos_summary.csv` | 拼起来的样本外 RankIC，按选择段 / 验证段汇总 |

---

## 6. 推断：`compute()` 怎么用这些模型

推断在 `sherpa/alpha/custom/ml/`，研究流水线的步骤 1~5（以后实盘也一样）都通过它拿打分：

```text
alpha.py           MLAlpha.compute(panel)：下面 ①~⑤
 ├─ manifest.py    load_manifest / Manifest.assign：读清单、给每一行分配模型
 ├─ features.py    build_features：算特征（和训练用的是同一个函数）
 └─ models.py      LgbmV1：类属性给出特征清单 spec 和模型名 model_name
```

逻辑上是"每一行找负责它的模型"，但实现上**不逐 bar 循环**，而是向量化一次分好组，再按模型循环（最多 68 次）：

```text
compute(panel):
  ① manifest = 读 manifest.json（每个 alpha 对象只读一次），校验特征指纹
  ② scope = spec.liquidity.mask(panel)：流动性范围，跟训练时同一份
     features = build_features(panel, spec, scope)
       整个面板一次算好：(行数, 特征数) 长表，每行一个 (时间, 币)
  ③ assigned = manifest.assign(每行的时间)
       二分查找，一次性给每一行一个模型编号：
       2024-07-09 00:00 ~ 2024-07-28 20:00 的行 → 第 37 号模型
       2022-06-30 之前的行 → -1（没有模型）
       流动性范围外的行 → -1（不打分）
  ④ for 每个用到的模型编号 i:              ← 循环次数 = 用到的模型数，不是 bar 数
       rows = 属于模型 i 的所有行（可能是几千行，跨 120 根 bar）
       一次喂给模型 i 的 3 个种子，预测取平均
       模型文件第一次用到时才加载，之后缓存在这个 alpha 对象里
  ⑤ 长表变回 (T, N) 宽表，没有模型或在范围外的格子为 NaN
```

几个细节：

- **按需加载**：阶段一只取到 2024-06-30，只会用到前 37 个模型，后面的模型文件不会被加载；
- **lightgbm 延迟 import**：在第一次加载模型时才 import。没装 ML 依赖时 `import sherpa.alpha.custom` 不受影响，只有真的
  算 ML alpha 才报错；
- **实盘**：`latest(panel)` = `compute(panel)` 取最后一行。实盘面板只有最近几百根 bar，`assign` 只会命中最新的那个模型，
  等价于"用最新模型给当前截面打分"。实盘的重训就是按同样的节奏往清单里追加新模型；
- **模型位置**：默认 `research/alpha_research/MLalpha/models/<model_name>/`，环境变量 `SHERPA_ML_MODEL_ROOT` 可以换根目录。

---

## 7. 时间对齐：为什么不会用到未来信息

以 2024-07-09 00:00 这根 bar 为例：

```text
1. 清单里负责它的模型：valid_from = 2024-07-09，valid_until = 2024-07-29
2. 这个模型只用了 <= 2024-07-08 16:00 的训练行，这些行的标签最晚用到 2024-07-09 00:00 的收盘价
3. 这根 bar 的特征只用 <= 2024-07-09 00:00 的数据
```

推论：

- 同一根 bar 的打分跟取数长度无关——阶段一只取到 2024-06-30、关卡3 取到 2026-03-15，算出来的完全一样
  （`tests/research/test_ml_training.py::test_ml_alpha_scores_are_point_in_time`）；
- 面板多几列还没上线的币，特征不变（`tests/alpha/test_ml_alpha.py::test_features_ignore_symbols_that_are_not_listed_yet`）；
- 第一个重训时点之前没有模型，打分为 NaN，相当于这个 alpha 的 warm-up。

---

## 8. 参数（`config.py`，所有 ML 研究线共用）

| 参数 | 当前值 | 含义 |
| --- | --- | --- |
| `RETRAIN_EVERY_BARS` | 120（20 天） | 多久重训一次，每个模型只服务到下一次重训 |
| `MIN_TRAIN_BARS` | 1080（180 天） | 第一次训练前至少要有的历史 |
| `TRAIN_WINDOW_BARS` | 360（60 天） | 滑动训练窗口；`None` = 扩展窗口（从研究起点用到 τ） |
| `INNER_VALID_BARS` | 120（20 天） | 窗口里最近这么多根 bar 做内部验证段（只用于早停；之后整窗重训） |
| `NEUTRALIZE_LABEL` | `False` | 标签是否先剥离 Beta / Size |
| `OBJECTIVE` | `"ic_ir"` | `"ic_ir"` 或 `"l2_rank"`（对照） |
| `TAIL_QUANTILE` / `TAIL_WEIGHT` | 0.2 / 3.0 | 首尾加权；`TAIL_WEIGHT = 1` 就是普通 IC |
| `MIN_PERIOD_ROWS` | 20 | 掩码内少于这么多个币的时期不参与损失 |
| `SEEDS` | (0, 1, 2) | 每个重训时点几个随机种子，推断取平均 |
| `NUM_BOOST_ROUND` / `EARLY_STOPPING_ROUNDS` | 500 / 50 | 最多多少棵树、多少轮不提升就停 |
| `LGB_PARAMS` | 见文件 | LightGBM 超参数，第一版是经验值，没调过 |

流动性范围（损失掩码）不在这里，在模型的 `spec.liquidity`（见 §3 ③）。改任何一项都要 `--force` 重训。

另外两项（2026-10-05 起）：`LABEL_HORIZON_BARS`（训练标签持有几根，`None` = 跟 `research_config.json` 一致）、`LABEL_TRANSFORM`（`"rank"` 截面排名 / `"raw_clip"` 原始收益 1%/99% 截尾）。

**按模型覆盖**：上表是默认值。某个模型要不一样，在它的类上写 `training_overrides`（键 = `config.as_dict()` 的键，拼错直接报错），`config.for_model()` 合并出这个模型的有效配置，写进它自己的清单、参与它自己的配置指纹。同一条研究线里的几个模型可以用不同的标签 / 种子 / 窗口，比如：

```python
class LgbmV2(MLAlpha):            # sherpa/alpha/custom/ml/models.py
    training_overrides = {"label_horizon_bars": 6, "label_transform": "raw_clip",
                          "seeds": list(range(9)), "train_window_bars": None}
```

| 模型 | 标签 | 窗口 | 种子 | 说明 |
| --- | --- | --- | --- | --- |
| `LgbmV1`（`custom.ml_lgbm_v1`） | 持有 1 根、截面排名 | 滑动 60 天 | 3 | 第一 / 第二版，全用默认值 |
| `LgbmV2`（`custom.ml_lgbm_v2`） | 持有 6 根、原始收益截尾 | 扩展 | 9 | 基线：探索实验结论（`MLalpha/experiments/FINDINGS.md`），之后的新模型都先跟它比 |

---

## 9. 目录结构

```text
research/ml_training/
  README.md         本文
  run_training.py   入口：取数 → 训练集 → 增量滚动训练 → 写清单 → 样本外自检
  config.py         训练参数（§8）
  data.py           取数（从 friction_test/data.py 拷贝后独立维护）
  dataset.py        标签、训练集、滚动时间表、内部验证切分
  objective.py      IC_IR 损失（LightGBM 自定义损失 + 早停指标）
  trainer.py        单个重训时点的训练；逐期 RankIC

sherpa/alpha/custom/ml/   推断侧（训练也用到其中的特征构建和清单读写）
  features.py       特征构建（训练和推断共用）
  manifest.py       模型清单
  alpha.py          MLAlpha：compute() = 算特征 → 每行找模型 → 推断
  models.py         注册的具体模型（LgbmV1、B 组世坤因子名单）
```

测试：`tests/research/test_ml_training.py`（损失梯度、时间表、训练到推断端到端）、`tests/alpha/test_ml_alpha.py`
（特征的 point-in-time、多几列未上线币不变、清单、MLAlpha 报错）。

---

## 10. 第一版的已知问题

第一次运行（2026-10-01）验证段样本外 RankIC 0.056（IR 0.34），但关卡3 扣费后几乎不赚钱。原因：

- 模型打分和 `vol_42` 的截面秩相关约 −0.6，基本是"买低波动、卖高波动"；
- 高波动币收益右偏，**中位**收益低、**平均**收益不低。排名标签和 RankIC 奖励的是中位数效应，Top-K 等权持仓赚的是
  平均收益，所以 IC 高却赚不到钱；
- 换成原始收益标签（1% 截尾）后首尾价差仍只有约 4 bps/期，说明这批特征对 4h 平均收益的预测力本身就弱；
- 每个模型都在 1~5 棵树就早停，也是同一个原因：第一棵树就把低波动倾向学完了。

所以看训练结果时**不能只看 RankIC**，还要看首尾价差、Pearson IC 和打分对波动率的暴露。损失和标签怎么改，见设计文档
后续讨论。

---

## 11. 探索实验（`run_experiments.py` / `evaluation.py`）

批量试配置用的工具，不改正式模型：每个 case 用跟正式训练相同的函数滚动训练、样本外打分，用关卡3 同口径的扣费回测比较
（Top-K 迟滞网格 × 调仓频率 × 成本 × 打分平滑），并输出 RankIC / Pearson IC / 首尾价差 / vol 暴露 / 空仓比例等诊断。
"打分 → 目标仓位 → 回测 → 分段绩效"这条链在 `sherpa.backtest.score_backtest`，跟关卡3 共用同一份实现（2026-10-05 重构，
前后结果逐项相同），`evaluation.py` 只放探索特有的平滑、诊断、多空两腿拆分和更宽的迟滞网格。
挑配置只看选择段、验证段只用来确认。case 定义在 `run_experiments.py` 的 `CASES`，结果在
`research/alpha_research/MLalpha/experiments/<case>/`，汇总 `summary.csv`，结论 `FINDINGS.md`。

```bash
python research/ml_training/run_experiments.py                       # 全部 case（第一次会从 ClickHouse 取数并缓存）
python research/ml_training/run_experiments.py --cases h6_raw         # 指定 case
python research/ml_training/run_experiments.py --skip-existing        # 跳过已跑完的
python research/ml_training/run_experiments.py --reeval               # 评估网格改了：读已有打分重新评估，不重训
python research/ml_training/run_experiments.py --summary-only         # 只重新汇总
```
