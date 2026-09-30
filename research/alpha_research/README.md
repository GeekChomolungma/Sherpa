# alpha_research/：按研究线（track）组织的研究流水线

每个子目录是一条**研究线（track）**：一份 `track.json` 说清楚"研究哪些因子、用什么处理链、看哪些 regime、
关卡1/2 真跑还是透传"，再加这条线自己的编排脚本 `run_track.sh`。**整条流水线（阶段一 → 汇总报告 → 关卡1/2/3）
的产出都归档在研究线目录下**，各关卡目录（`factor_orthogonalization/` 等）只放代码，是所有研究线共用的通用
中间流程模块。不同研究线互不覆盖。

| 目录 | 说明 |
|---|---|
| [`_pipeline/`](_pipeline/) | 各研究线共用的阶段一工具：`run_profile.py`（通用的 Regime 条件 IC 体检）、`data.py`（取数）、`lib.sh`（编排脚本共用的 bash 工具） |
| [`../_shared/`](../_shared/) | 阶段一和各关卡都要用的两个模块：`track.py`（读研究线配置）、`handoff.py`（阶段之间的交接格式） |
| [`worldquant_101/`](worldquant_101/) | 世坤101 全量因子，全流程样板：关卡1/2 真跑。编排 `run_track.sh`（根目录 `run_research.sh` 转发到这里） |
| [`custom_starter/`](custom_starter/) | 自定义因子 starter 主题（`sherpa/alpha/custom/starter.py`），只看 trend；因子少，关卡1/2 透传，直接进关卡3 |
| [`custom_quote_activity/`](custom_quote_activity/) | 成交活跃度排名单因子（`sherpa/alpha/custom/quote_activity.py`），只看 trend；关卡1/2 透传，直接进关卡3 |

## 流水线：各阶段只靠交接文件（handoff）连接

```text
阶段一 run_profile ─> 汇总报告 ──report.json──> 关卡1 ──orthogonalization.json──> 关卡2 ──synthesis.json──> 关卡3
                     (候选集)                   (候选集)                            (配方集)
```

**生产者有义务按标准格式输出，消费者只认标准格式**（`research/_shared/handoff.py`）。整条流水线只有两种交接物：

- **候选集**（candidates）：`{维度: {state: 因子列表}}` + 不分 regime 的全局名单。汇总报告产出；关卡1 吃它、
  再产出去冗余后的它（关卡1 本质是候选集过滤器）；关卡2 吃它。
- **配方集**（recipes）：冻结配方，static（一组带符号权重）或 routed（按某个 regime 维度的 state 切换权重）。
  关卡2 产出，关卡3 吃。

每个阶段固定读前一阶段的 `<研究线>/handoff/<阶段>.json`、写自己的那份。所以**跳过某一关 = 让它透传**：

| 关卡 | `mode: "run"` | `mode: "passthrough"` |
|---|---|---|
| 关卡1 正交化 | 按 state 切片去冗余，保留名单写成候选集 | 不取数，输入候选集原样转交 |
| 关卡2 合成 | 各合成方案在验证段上比较，全部方案 + 最强单因子冻结成配方集 | 不取数，候选集直接变成等权配方（`直通·` 前缀，`factor_synthesis/passthrough.py`） |
| 关卡3 摩擦 | 所有研究线都必须真跑 | — |

透传同样产出标准交接文件，下游感知不到差别，编排脚本也不用为跳关写分支。

**手动干预**：交接文件是 JSON，人可以直接改（比如删掉某个候选因子、改一个配方的权重），改完 `--from-step`
从下一步续跑。以前 `run_research.sh --refresh-*` 那套"刷新候选池"开关已经没有了。

## 研究线目录里有什么

```text
<track>/
  track.json                  研究线配置
  run_track.sh                编排脚本
  regime_alpha_profile.csv    阶段一长表
  handoff/                    report.json / orthogonalization.json / synthesis.json
  results/
    report/                   汇总报告（04_regime_matrix.csv 等）
    orthogonalization/        关卡1 明细（透传时没有）
    synthesis/                关卡2 明细（透传时没有）
    friction/                 关卡3 明细（02_validation_base_cost.csv 先看这张）
```

`preprocess.neutralize=false` 的对照模式整套换名：`regime_alpha_profile_without_neutralization.csv`、
`handoff_without_neutralization/`、`results_without_neutralization/`，不会覆盖标准版本。

## family 和 track 的区别

- **family**（`worldquant` / `custom` …）：因子**从哪来**，是 sherpa 层的概念，写在因子类上。
- **track**：这一轮研究**怎么做**，是 research 层的概念，写在 `track.json` 里。

两者正交：一条 track 可以只收 custom 的某个主题模块，也可以同时收 worldquant 和 custom 的因子（比如专门检验
"自定义因子跟世坤因子冗不冗余"）。下游关卡只认 qualified_name（`family.name`），不关心因子来自哪条研究线。

## track.json 字段

```json
{
  "id": "custom_starter",
  "description": "一句话说明",
  "alphas": { "modules": ["sherpa.alpha.custom.starter"], "family": "custom" },
  "preprocess": { "tradable_mask": true, "neutralize": true },
  "regime": { "dimensions": ["trend"] },
  "report": { "matrix_top_k": 5, "min_abs_t": 3.0 },
  "stages": {
    "orthogonalization": { "mode": "passthrough" },
    "synthesis": { "mode": "passthrough", "passthrough": { "singles": true, "equal_weight": true, "routed": true } }
  }
}
```

| 字段 | 含义 |
|---|---|
| `id` | 研究线 id，必须等于目录名 |
| `alphas.modules` | 因子模块路径列表：会被 import（触发注册），并且只收**定义在这些模块及其子模块里**的因子（按 `cls.__module__` 判断） |
| `alphas.family` | 可选，再按 family 过滤 |
| `preprocess.tradable_mask` | 外层可流通性掩码：`true` = `tradable_mask` 默认门槛，`false` = 不掩码，对象 = 覆盖部分门槛参数（如 `{"min_percentile": 0.6}`）。阶段一和关卡1/2/3 都用它 |
| `preprocess.neutralize` | 是否剥离 Beta/Size 暴露，阶段一和各关卡都用它。`false` 是对照模式（整套产出换名，见上） |
| `regime.dimensions` | 阶段一条件 IC 切哪些维度，取值见 `sherpa.metrics.regime.REGIME_STATES`；省略 = 全部四个。下游的 state 名单、关卡2 的路由维度都跟着候选集走 |
| `report.matrix_top_k` / `report.min_abs_t` | 汇总报告每个 state 取前几名、显著性门槛（环境变量 `MIN_ABS_T` 可临时覆盖） |
| `stages.orthogonalization.mode` / `stages.synthesis.mode` | `run`（默认）或 `passthrough`，见上表 |
| `stages.synthesis.passthrough` | 关卡2 透传时出哪些配方：`singles`（true = 每个候选因子一个单因子配方；整数 N = 按全历史 \|IC_IR\| 取前 N 个）、`equal_weight`（`直通·G0` / `直通·L0`）、`routed`（每个维度一个 `直通·L2-<维度>`） |

**track 不能覆盖的**：时间窗、IC 标签口径（horizon / delay）、大盘锚点、成本，统一在
`research/research_config.json`。不同研究线的结论要能横向比较，这几项必须一致。关卡自身的参数（相关性阈值、
调仓网格、验收红线）在各关卡的 `config.py`，所有研究线共用。

处理链（掩码 → 中性化）本身在 `sherpa.backtest.residual`，track 只决定开关和门槛。注意这是**外层**掩码；因子
公式里想只在流动性好的子集里做截面运算，是因子自己在 `compute()` 里用 `tradable_mask`，跟这一层互不替代。

## 新开一条研究线

1. 在 `sherpa/alpha/custom/<主题>.py` 写因子（继承 `CustomAlpha` 或用 `@custom_alpha`），在
   `sherpa/alpha/custom/__init__.py` 里 import 它；
2. 复制 `custom_starter/` 成 `<新 track>/`，改 `track.json` 的 `id`（= 目录名）、`alphas.modules`、其它开关；
3. `bash research/alpha_research/<新 track>/run_track.sh --dry-run` 看一遍命令，再去掉 `--dry-run` 正式跑。

因子积累多了、想做去冗余 / 合成对比时，把 `stages` 里对应的关卡改成 `run`，从关卡1 那一步 `--from-step` 续跑即可。
