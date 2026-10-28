# research/viz：研究结果可视化

把研究线 run 目录（`research/alpha_research/<研究线>/runs/<run_id>/`）里的逐期数据画成**横轴是时间**的图，输出单个 HTML 文件，
双击用浏览器打开就能看（可缩放时间轴、鼠标悬停同时看各条线的数值），不用起服务。

两种画布：

| 命令 | 画什么 | 适合回答 |
| --- | --- | --- |
| `run` | **一个 run 的总览**：滚动 RankIC、累计 RankIC、净值（附全部组合的分布带）、回撤、滚动净 Sharpe、换手，上下共用时间轴 | 这个模型的排序能力什么时候强 / 弱、有没有衰减，收益和回撤是不是跟着 RankIC 走 |
| `compare` | **多个 run 的同一批指标放一张图**：一个指标一行，每条线是一个模型 | 几个模型谁的 RankIC 更高、差距是稳定的还是只在某段时间，同一个组合下谁的回撤更小 |

读图的原则跟 [`alpha_research/MLalpha/RESULT_READING.md`](../alpha_research/MLalpha/RESULT_READING.md) §0 一致：**RankIC 是主判据，收益只作确认**，所以 RankIC 总在最上面。

---

## 1. 安装

```bash
pip install -e .[viz]      # plotly
```

## 2. 先决条件：run 里要有逐期文件

可视化只读文件，不重算。需要的三份文件是 2026-10-27 起研究线才落盘的：

| 文件 | 谁写的 | 内容 |
| --- | --- | --- |
| `results_without_neutralization/ml_training/<model>_ic_by_bar.csv` | 步骤 0 训练（`research/ml_training/run_training.py`） | 每根 bar 一行的样本外 RankIC（6 根标签）、这一期的币数、负责它的重训时点、所属段 |
| `results_without_neutralization/friction/07_bar_gross_returns.csv` | 关卡3（`research/friction_test/run_friction.py`） | 全部 39 个组合、整个研究段（选择段 + 验证段）的逐 bar 毛收益，列 = 组合 |
| `results_without_neutralization/friction/08_bar_turnover.csv` | 同上 | 同样形状的逐 bar 单边换手 |
| `results_without_neutralization/friction/bar_series.json` | 同上 | 各成本假设的 bps、验证段起点 |

旧 run 没有这些文件，重跑一次研究线就有了。ML 模型已经训练好时步骤 0 只做评估、不重训，几分钟就够：

```bash
CH_HOST=... CH_PASSWORD=... bash research/alpha_research/MLalpha/run_track.sh --alphas custom.ml_lgbm_v4
# 只缺关卡3 的文件时：  ... run_track.sh --alphas custom.ml_lgbm_v4 --from-step 5
```

非 ML 的研究线没有 `ml_training/`，总览里 RankIC 两行会写"无数据"，收益部分照常画。

### 市场背景（BTC 收盘价）

两种画布的最上面一行默认画 BTCUSDT 的收盘价（对数刻度），用来对照"行情怎么走的时候，RankIC 和收益是什么样"。它是市场数据，
跟哪个 run 无关，所以**不放进 runs**，单独取到 `research/viz/market/`：

```bash
CH_HOST=... CH_PASSWORD=... python research/viz/fetch_market.py            # -> research/viz/market/BTCUSDT_4h.csv
CH_HOST=... CH_PASSWORD=... python research/viz/fetch_market.py ETHUSDT    # 别的币，画图时 --market ETHUSDT
```

时间范围 = `research_config.json` 的研究段，**不取 holdout 段**。CSV 不进 git（跟其它 CSV 一样），换机器重新取一次。没取过的话
图里就不画这一行（命令行会提示），其它照常。

为什么单独一行、不叠到 RankIC 或净值图上：价格和 RankIC / 净值的量纲完全不同，叠在一起只能用两个纵轴，两条线看起来"同步"还是"背离"
完全取决于两个纵轴怎么缩放，很容易看出不存在的关系。单独一行、共用时间轴，沿同一条竖线往下看就能对上，鼠标悬停时同一时刻的
BTC 价格和各指标一起显示。

## 3. 用法

以下命令都在仓库根目录跑。

### 3.1 一个 run 的总览

```bash
python research/viz/viz.py run research/alpha_research/MLalpha/runs/lstm_v5
```

输出 `research/viz/output/runs/lstm_v5.html`，同时在终端打印分段小结（平均 RankIC、净 Sharpe、最大回撤、累计收益）。
一次给多个目录，每个 run 各出一页。

### 3.2 多个模型放一张图

```bash
R=research/alpha_research/MLalpha/runs
python research/viz/viz.py compare $R/lgbm_v4 $R/xgb_v5 $R/lstm_v5 --baseline lgbm_v4
```

输出 `research/viz/output/compare/lgbm_v4+xgb_v5+lstm_v5.html`。默认画 5 个指标：

| 指标名 | 画的是什么 | 怎么看 |
| --- | --- | --- |
| `rankic_cum` | 累计 RankIC（逐期 IC 的累加） | 斜率就是 IC 水平；斜率变平 = 排序能力衰减。比滚动均值稳，最适合看长期趋势 |
| `rankic_diff_cum` | 每个模型减去基线同一期 IC 后的累加（要 `--baseline`） | 向上 = 这段时间比基线好，向下 = 比基线差；拐点就是优势开始 / 结束的时间 |
| `rankic_rolling` | 滚动 RankIC（默认 20 天均值） | 看短期波动，跟季度行情对照 |
| `equity` | 选定组合、选定成本下的净值 | 只作确认：收益是不是跟着 RankIC 走 |
| `drawdown` | 同一条净值的回撤 | 最大回撤出现在什么时候、各模型是不是同时回撤 |

另外可选 `sharpe_rolling`（滚动净 Sharpe，默认 90 天）、`turnover`（单边换手，20 天均值）。自己挑：

```bash
python research/viz/viz.py compare $R/lgbm_v4 $R/lstm_v5 --metrics rankic_cum equity drawdown turnover
```

一张图最多 8 个模型（颜色按固定顺序分配、不循环，第 1 个模型永远是蓝色）；同一个模型在各行是同一个颜色。

### 3.3 换组合、换成本

PnL 一律是**同一个组合**下的结果，不会各模型各挑最好的那格（那等于在验证段上挑过一遍，比较就不公平了）。默认组合写在
`series.py` 顶部：

```python
DEFAULT_WEIGHTING = "top10_exit20"   # 权重映射：做多 / 做空各前 10 名，跌出前 20 才换
DEFAULT_REBALANCE_EVERY = 6          # 每 6 根 bar（1 天）调一次仓
DEFAULT_COST = "all_taker"           # 全吃单成本（手续费 + 滑点，单边 8 bps）
```

临时换用命令行参数，所有模型同步切换：

```bash
python research/viz/viz.py compare $R/lgbm_v4 $R/lstm_v5 --weighting top20_exit60 --every 6 --cost all_maker
python research/viz/viz.py run $R/lgbm_v4 --list-combos      # 列出 run 里有哪些组合
```

不是默认组合时，输出文件名会带上组合和成本（如 `lgbm_v4+lstm_v5__top20_exit60_every6_all_maker.html`），不会覆盖默认那份。
成本假设有 `zero`（零成本，即毛收益）/ `all_maker` / `all_taker` / `stress`，bps 读自 `bar_series.json`。

### 3.4 其它参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `--ic-window` | 20 | 滚动 RankIC 窗口（天）；总览里另有一条 120 天的 |
| `--sharpe-window` | 90 | 滚动 Sharpe 窗口（天） |
| `--case` | — | 一个 run 里有多个 case（`--alphas a,b` 一起评估）时指定看哪一个 |
| `--market` | `BTCUSDT` | 最上面一行的市场背景；`none` = 不画 |
| `--out` | `research/viz/output/` | 输出目录，或直接给一个 `.html` 文件名 |
| `--name` | 各 run 名用 `+` 连起来 | `compare` 的输出文件名 |

## 4. 图上的元素

- **最上面一行** = 市场背景（BTC 收盘价，对数刻度）；
- **灰色背景** = 验证段（之前是选择段）。选择段是挑模型、挑特征的那段，数字偏乐观；验证段是确认用的；
- **细竖线** = ML 模型的重训时点（每 20 天一个）；
- **总览的净值行**：蓝线 = 选定组合的净值，橙色虚线 = 同一组合零成本的毛净值（两者的差 = 成本吃掉的部分），灰带 = 全部 39 个组合
  净值的 25%–75% 分位，灰色点线 = 中位数。选定组合远在灰带之上 / 之下，说明它的表现靠的是"挑到了这个组合"；
- **顶部的表**：按段的小结，`compare` 里每个模型每段一行；
- **多模型对比的时间轴**裁到所有模型都有数据的共同区间，累计类曲线（累计 RankIC、净值、回撤）从同一个起点出发。

## 5. 输出放在哪

默认写到 `research/viz/output/`（`runs/` 放总览，`compare/` 放对比）。跟 runs 里的结果分开放：runs 是研究线的产出（元数据），
这里是从它派生的图，随时可以删了重新生成。HTML 不进 git（`.gitignore`），跟 runs 里的 CSV 一样。

## 6. 代码结构（以后接阶段二）

| 文件 | 职责 |
| --- | --- |
| `series.py` | 数据层：`RunSeries`（一个 run 的逐期 RankIC、逐 bar 毛收益和换手、成本口径、分段、事件时点）和加载器；默认组合常量 |
| `metrics.py` | 从底层序列派生指标（净收益、净值、回撤、滚动 Sharpe、累计 / 滚动 RankIC）；多模型比较的指标表 `METRICS` |
| `figures.py` | 两种画布（plotly）和 HTML 页面 |
| `viz.py` | 命令行入口 |
| `fetch_market.py` | 从 ClickHouse 取市场背景（收盘价）到 `market/` |

画图只认 `RunSeries`，不关心数据是哪个阶段产出的。以后接阶段二回测：在 `series.py` 里加一个加载器，把回测结果（`sherpa/backtest`
的 `BacktestResult` 本来就有逐 bar 收益和换手）填进 `RunSeries`，在 `load_run` 里按目录结构分派过去，画图和命令行都不用改。
加新指标：在 `metrics.py` 的 `METRICS` 里加一项（标题、纵轴名、取哪条底层序列、怎么派生）。
