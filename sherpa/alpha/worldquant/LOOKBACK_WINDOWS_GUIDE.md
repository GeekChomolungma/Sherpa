# 世坤101因子回看窗口说明

> 配套脚本：[`lookback_windows.py`](lookback_windows.py)。本文档只解释"每种算子的窗口参数
> 业务上代表什么"，不列具体因子的具体数值——数值会随你调整窗口而变，跑脚本看当前真实值，
> 不要看这份文档里的例子当作最新状态。

## 背景

世坤101论文按美股日频校准了每个因子里的窗口（"5日反转""200日均线"这类），这些整数直接
写死在每个 `Alpha.compute()` 方法内部，没有集中到共享配置——`docs/LOOKBACK_WINDOW_MIGRATION.md`
§3 记录了从 1d 切到 4h 时这一块要怎么处理（结论：不建统一换算层，保留因子自己的窗口，按需
逐个判断）。这份文档 + 脚本是那个决策的配套工具：**不自动改任何东西，只负责让你随时看清楚
"现在每个因子里到底散落着哪些窗口参数、各自是什么意思"**，作为你定期核查/决定要不要调整
某个窗口时的参考。

## 怎么跑

```bash
python -m sherpa.alpha.worldquant.lookback_windows              # 全量打印
python -m sherpa.alpha.worldquant.lookback_windows --min 20     # 只看最长窗口 >= 20 根的因子
python -m sherpa.alpha.worldquant.lookback_windows --csv out.csv  # 额外写一份 CSV，方便筛选/存档对比
```

不需要连 ClickHouse——纯静态扫描源码（`ast` 解析每个因子 `compute()` 方法的源码文本），
随时能跑，跑完看到的永远是当前代码的真实状态。`industry/` 行业组按你的要求被排除，脚本只扫
`price_volume`/`momentum_reversal`/`microstructure`/`composite` 四个家族。

## 算子窗口参数的业务含义（速查表）

| 算子 | 参数位置 | 业务含义 | 是否受"跨symbol价格量级"问题影响 |
|---|---|---|---|
| `ops.ts_sum(x, window)` | 第2个位置参数 | 窗口内求和，常见于均线分子（`sum(close,N)/N`）或窗口累计量 | 取决于 x 本身是不是价格量纲 |
| `ops.ts_min(x, window)` / `ts_max` | 第2个位置参数 | 窗口内最小/最大值，常见于"距自身滚动低点/高点距离"类特征 | 同上 |
| `ops.stddev(x, window)` | 第2个位置参数 | 窗口内标准差，衡量该字段在窗口内的离散/波动程度 | x 是价格则受影响（应该传 x 的收益率而不是价格本身，见 `_common.rank_price` 的中性化处理原则） |
| `ops.ts_product(x, window)` | 第2个位置参数 | 窗口内累乘 | 取决于 x |
| `ops.ts_rank(x, window)` | 第2个位置参数 | **逐 symbol 自比较**的时序百分位排名——只跟这个 symbol 自己的历史比，不跨 symbol 比较 | **不受影响**，天然安全（`_common.rank_price` docstring 里解释过的道理） |
| `ops.ts_argmax(x, window)` / `ts_argmin` | 第2个位置参数 | 窗口内极值出现的位置索引（`0~window-1`），本身是无量纲整数，不是极值本身 | **不受影响** |
| `ops.ts_corr(x, y, window)` | 第3个位置参数 | 窗口内两个序列的滚动皮尔逊相关系数 | **不受影响**（相关系数对每条腿的线性缩放不敏感），除非某条腿本身先被 `ops.rank()` 排过绝对价格 |
| `ops.ts_cov(x, y, window)` | 第3个位置参数 | 窗口内两个序列的滚动协方差 | 不像相关系数那样自带缩放，看 x/y 是否已经是无量纲量 |
| `ops.decay_linear(x, window)` | 第2个位置参数 | 线性衰减加权移动平均，窗口内越新的数据权重越大 | 取决于 x |
| `ops.adv(volume, window)` | 第2个位置参数 | 窗口内平均成交量（论文里的 `adv{d}`，`d` 原本按天） | 成交量量级问题，本仓库现阶段视为可接受（见 `QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` 中性化章节的范围界定） |
| `ops.delay(x, periods)` | 第2个位置参数 | 取 `periods` 根之前的值，纯移位，不是滚动窗口统计量 | 取决于 x |
| `ops.delta(x, periods)` | 第2个位置参数 | 跟 `periods` 根之前的差值（绝对差） | x 是价格则受影响；本仓库中性化改造已经把大部分这类用法换成了 `pct_change` |
| `.pct_change(periods=N)` | 关键字/第1个位置参数 | 跟 N 根之前的百分比涨跌幅——中性化改造引入的安全替代 | **不受影响**，这正是安全版本 |
| `rank_price(price, periods=1)`（`_common.py`） | 关键字/第2个位置参数 | 截面排名前先做 `pct_change` 归一化的安全替代 | **不受影响** |
| `rank_price_distance_from_low(price, window)`（`_common.py`） | 关键字/第2个位置参数 | 距自身滚动最低点的百分比距离 | **不受影响** |
| `rank_price_diff(a, b, reference)`（`_common.py`） | 无单一整数窗口 | 两个不同价格字段差值的安全替代，用显式 `reference` 归一化；脚本会把这一行单独标注，不强行凑一个数字 | **不受影响** |

## 怎么读输出

```
worldquant.alpha013  (min_lookback=5)
  L 113  rank_price(1)  — 截面排名前先做 pct_change 归一化的安全替代，见 _common.rank_price
  L 113  ts_cov(5)  — 窗口内两个序列的滚动协方差（不像相关系数那样自带缩放）
```

- 第一行是因子的 `qualified_name` 和类属性 `min_lookback`（大致等于该因子内部最长窗口+1，
  用来快速筛选"哪些因子受影响最大"）。
- 每一行 `L<行号> 算子(参数值) — 业务含义`，行号是 `sherpa/alpha/worldquant/<family>/alphas.py`
  里的真实行号，可以直接跳过去看上下文。
- 参数值解析不出具体整数时会显示成源码文本（比如引用了一个变量而不是字面整数）——目前
  仓库里所有窗口都是字面整数，理论上不会出现这种情况，出现了说明这个算子用法比较特殊，
  建议人工确认。
- `[占位/禁用因子：compute() 直接 raise NotImplementedError，无窗口属正常]`——这是
  `alpha056`/`alpha046`/`alpha049`/`alpha051`/`alpha047` 这 5 个（分别因为缺市值数据、
  阈值缺乏原则性依据、"低价股效应"经济假设不成立而禁用，见各自 docstring），脚本自动识别，
  不是遗漏。

## 这份工具不做什么

- 不判断"这个窗口该不该跟着频率换算"——这是需要结合因子经济含义人工判断的问题，
  `docs/LOOKBACK_WINDOW_MIGRATION.md` §3.1 有完整论证。
- 不自动改代码，纯只读扫描。
- 不产出需要手动维护的快照文件（`--csv` 是可选的，导出即时状态方便你自己存档/diff，
  不是脚本自己维护的产物）。
