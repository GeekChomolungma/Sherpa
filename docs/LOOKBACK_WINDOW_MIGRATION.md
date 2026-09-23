# 频率迁移手册：从 1d 切到 4h，所有回看窗口/滚动统计的波及面

> 本文档记录 Sherpa 从"日线（1d）"研究切换到"4小时（4h）"研究时，阶段一（单因子体检）到
> 关卡1（正交化，含已并入阶段一的中性化）范围内，所有隐式按"日历天数"校准的回看窗口、
> 滚动均值/中位数窗口、以及少数受频率影响的绝对阈值——每一处的代码位置、业务含义、当前
> 状态（已改 / 待决策）。范围之外（阶段二回测、阶段三/四实盘）单独在 §5 说明影响机制，
> 不在本次迁移范围内。

---

## 目录
1. [背景：为什么 1d → 4h 不是简单改个字符串](#1-背景为什么-1d--4h-不是简单改个字符串)
2. [已完成的改动](#2-已完成的改动)
3. [尚待决策：世坤101因子内部窗口](#3-尚待决策世坤101因子内部窗口)
4. [Low-sample 阈值（受频率间接影响）](#4-low-sample-阈值受频率间接影响)
5. [`sherpa/data/` 数据层：现在不影响，未来何时会影响](#5-sherpadata-数据层现在不影响未来何时会影响)
   - [5.1 现在为什么不受影响](#51-现在为什么不受影响)
   - [5.2 `window_size`：Redis 来源，只在启动时"一波拉"](#52-window_sizewindowcache专属-interval1m redis-来源只在启动时一波拉)
   - [5.3 `lookback_bars`：ClickHouse 来源，含义因类而异](#53-lookback_barshistoricalpanelsourcelivepanelsourceclickhouse-来源含义因类而异)
   - [5.4 一句话区分](#54-一句话区分)
6. [代码位置速查表](#6-代码位置速查表)

---

## 1. 背景：为什么 1d → 4h 不是简单改个字符串

Sherpa 的很多统计量（可流通性掩码、regime 打标、beta 中性化、世坤101因子本身）都用 `.rolling(N)`
这类"过去 N 根 bar"的滚动窗口实现。这些 `N` 在最初实现/校准时，隐式假设了"1 根 bar = 1 个交易日"
——把数据源从 1d 切到 4h（1 天 6 根 bar）之后，同一个字面数字 `N` 所代表的**真实日历时间跨度缩水到了
原来的 1/6**，如果不重新校准，所有"N 天窗口"类的统计口径都会被悄悄压缩成"N/6 天"，跟原始设计意图
不符。

历史插曲（供参考）：`research/REGIME_FRAMEWORK_GUIDE.md`/`REGIME_ALPHA_EVALUATION_WORKFLOW.md`
这两份方法论文档最初就是按 4h（`rolling_quantile_window=540` ≈ 90天×6根/天）设计的，后来
`sherpa/metrics/regime.py` 落地实现时改成了 1d 语境（`DEFAULT_LOOKBACK=30`，注释明写"~30天@1d bar"），
但 `sherpa/backtest/regime_screening.py` 的入口函数又把 `ma_period` 单独覆盖回了 4h 语境的 `60`——
这次迁移之前，这三处本来就已经互相不一致。见 §2 表格，这个问题现在已经通过统一常量解决。

---

## 2. 已完成的改动

以下改动已经落地（本文档记录现状，不是待办）：

| 模块 | 参数 | 旧值（1d） | 新值（4h，约20天=120根） | 代码位置 |
|---|---|---|---|---|
| 可流通性掩码 | `DEFAULT_LOOKBACK` | 10 | **120** | [`sherpa/metrics/tradability.py:18`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/tradability.py#L18) |
| 可流通性掩码 | `SEASONING_PERIOD`（冷启动缓冲） | 10（原本跟 `DEFAULT_LOOKBACK` 绑定） | **20**（拆成独立常量，不再跟 `DEFAULT_LOOKBACK` 绑定） | [`tradability.py:19`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/tradability.py#L19) |
| Regime 打标 | `DEFAULT_LOOKBACK`（波动率/离散度/流动性三个维度的滚动分位数窗口，以及 `compute_trend_regime`/`build_regime_report` 的 `ma_period`/`vol_window` 全部统一指向同一个常量） | 30（`compute_trend_regime` 的 `ma_period` 另外还各自维护过 30/60 两套不一致的默认值） | **120**，四个维度、`ma_period`、`vol_window` 现在全部共用同一个常量，三处不一致已解决 | [`sherpa/metrics/regime.py:26`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/regime.py#L26)，透传见 [`regime_screening.py:34-36`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/regime_screening.py#L34-L36) |
| Beta 中性化 | `DEFAULT_BETA_WINDOW` | 90 | **120** | [`sherpa/risk/exposure.py:14`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk/exposure.py#L14) |
| Research 数据入口 | `INTERVAL` | `"1d"` | **`"4h"`** | [`research/alpha_research/worldquant_101/data.py:26`](file:///d:/code-repo/Chomo/Sherpa/research/alpha_research/worldquant_101/data.py#L26)、[`research/factor_orthogonalization/data.py:24`](file:///d:/code-repo/Chomo/Sherpa/research/factor_orthogonalization/data.py#L24)、[`research/tradability_calibration/data.py:29`](file:///d:/code-repo/Chomo/Sherpa/research/tradability_calibration/data.py#L29) |

**换算口径**：新值统一按"约20个日历天 × 6根/天(4h) = 120根"确定，除了 `SEASONING_PERIOD` 单独定为
20 根（约3.3天）冷启动缓冲，是刻意跟主窗口脱钩的独立选择，不是遗漏。

---

## 3. 尚待决策：世坤101因子内部窗口

**这是影响面最大、也是唯一还没动的部分。** `sherpa/alpha/worldquant/` 下 4 个家族文件（不含已经
按你的要求隔离的 `industry/` 组）里，**82 个非占位因子中约 48 个（~59%）内部至少嵌了一个 ≥20 根的
滚动窗口**，这些窗口是 `ops.ts_sum`/`ts_corr`/`ts_cov`/`ts_rank`/`ts_min`/`ts_max`/`decay_linear`/
`ops.adv` 调用时直接写死的整数常量，来自世坤101原始论文按美股日频校准的设计，散落在每个 `Alpha`
类的 `compute()` 方法内部，不经过任何共享常量。

### 3.1 是否要建统一换算层：结论是不建

详细论证见对话记录，结论摘要：
- 世坤因子的窗口分两类——长窗口（60~250根，均线/长期相关/`adv60`/`adv180` 这类，经济含义确实是
  "N个日历天"，理应跟着频率换算）和短窗口（2~10根，"最近几次波动的即时反应"，换算成 4h 后是保持
  "N根"还是换算成"N天对应的根数"是两种不同的经济假设，不是单纯量级换算）。全局统一乘数会把这两类
  混在一起处理，短窗口那批的经济含义会被强行改变。
- 4h 下每个窗口到底该多长，最终要靠阶段一 IC 体检结果验证，是经验问题，不是纯数学换算能替代的。
- 跟仓库一贯的"显式维护、每次改动可审查"架构态度一致（`factor_orthogonalization/README.md` 里的
  "候选池不自动继承体检结果"是同一种考虑）。

### 3.2 范围概况（不逐因子列出，按家族给范围）

| 家族文件 | 因子数 | 窗口范围（根） | ≥20根的因子数 | <10根（短窗口）的因子数 |
|---|---|---|---|---|
| [`price_volume/alphas.py`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/worldquant/price_volume/alphas.py) | 28 | 1~250 | 14 | 9 |
| [`momentum_reversal/alphas.py`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/worldquant/momentum_reversal/alphas.py) | 25 | 1~250 | 16 | 7 |
| [`microstructure/alphas.py`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/worldquant/microstructure/alphas.py) | 18 | 1~73 | 8 | 4 |
| [`composite/alphas.py`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/worldquant/composite/alphas.py) | 12 | 1~230 | 10 | 0 |

每个 `Alpha` 类的 `min_lookback` 类属性基本能代表它内部最长窗口+1，可以按这个字段筛出"哪些因子受
影响最大"作为排查起点。`ops.adv(volume, N)`（N日平均成交量）这个子表达式贯穿 `price_volume`/
`momentum_reversal` 两个文件里的几十个因子，`N ∈ {20,30,40,50,120,180}`，是同一批因子共享的构建块，
值得优先考虑统一处理。

### 3.3 建议的推进方式

不建自动生效的隐式层，但配了一个一次性、可审查的辅助工具：
[`sherpa/alpha/worldquant/lookback_windows.py`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/worldquant/lookback_windows.py)
（说明见同目录 [`LOOKBACK_WINDOWS_GUIDE.md`](file:///d:/code-repo/Chomo/Sherpa/sherpa/alpha/worldquant/LOOKBACK_WINDOWS_GUIDE.md)）。
纯静态扫描每个因子 `compute()` 里的窗口调用，打印算子+参数值+业务含义+真实行号，不连
ClickHouse、不自动改代码，`--min N` 可以只看最长窗口 ≥N 的因子，`--csv` 可以导出存档/diff：

```bash
python -m sherpa.alpha.worldquant.lookback_windows --min 20
```

人工确认哪些窗口参与换算、换算成多少之后，再逐个改。

---

## 4. Low-sample 阈值（受频率间接影响）

不是回看窗口，但语义会被频率间接改变——判断"某个 regime state 的样本是否充分"的绝对根数门槛，
攒够门槛所需的日历时间会随频率提高而缩短：

| 代码位置 | 参数 | 当前值 | 业务含义 |
|---|---|---|---|
| [`research/factor_orthogonalization/config.py:157-158`](file:///d:/code-repo/Chomo/Sherpa/research/factor_orthogonalization/config.py#L157-L158) | `LOW_SAMPLE_MIN_SAMPLES` / `LOW_SAMPLE_MIN_FRACTION` | 100 / 0.10 | 某个 (dimension, state) 切片样本数低于此判"低样本警告"。4h 下攒够 100 根只需要 1d 下的 1/6 日历时间，"这个 state 是否被充分验证过"的统计意义变了，即使字面数字不变 |
| [`research/regime_factor_report/regime_factor_report.py:174-175`](file:///d:/code-repo/Chomo/Sherpa/research/regime_factor_report/regime_factor_report.py#L174-L175) | `low_sample_abs` / `low_sample_fraction` | 100 / 0.10 | 同上，同一套口径 |

**未改动，留给你决定**：是否需要相应调大这两个阈值（比如同步乘以6，保持"多少日历天算充分样本"的
原意），还是保留字面值不变（相当于放宽了"充分样本"的日历时间要求）。

---

## 5. `sherpa/data/` 数据层：现在不影响，未来何时会影响

`sherpa/data/panel_source.py`（`HistoricalPanelSource.lookback_bars`、`LivePanelSource.lookback_bars`/
`window_size`）和 `sherpa/data/window_cache.py`（`WindowCache.window_size`）**这次迁移完全没有触碰**。
这几个参数名字很像，但其实是两套完全不同的机制，容易搞混，分开说。

### 5.1 现在为什么不受影响

`research/*/data.py` 的 `load_universe_panel()` 是直接 `ch_reader.fetch_history(start_time=START_TIME,
end_time=END_TIME)` 一次性拉整个区间，**完全不经过** `HistoricalPanelSource`/`LivePanelSource`/
`WindowCache`——这几个类只在阶段二（回测，`sherpa.backtest.event_driven.Simulator`）和阶段三/四
（实盘）才会被用到，现在都不在研究脚本的调用链路里，改不改对现在的工作零影响。

### 5.2 `window_size`（`WindowCache`，专属 `interval="1m"`）：Redis 来源，只在启动时"一波拉"

- `seed()`：启动时从 Redis 的 `kline:{SYM}:1m`（这个 Redis List 在生产端本身就固定只保留最近
  200 根，见 [`docs/DATA_CONSUMER_GUIDE.md`](file:///d:/code-repo/Chomo/Sherpa/docs/DATA_CONSUMER_GUIDE.md)）
  一次性拉 `window_size`（默认200）根，填满内存里的初始窗口——这是唯一"一波拉很多根"的地方。
- 之后每来一次 `kline_ready` 通知（每分钟一次），**不会再重新拉 200 根**，只拉最新那**一根**新收盘的
  bar（`get_latest_closed_bars`），追加进内存，超过 200 根就把最老的一根挤出去——是个在 Python
  进程内存里维护的滑动环形缓冲区，增量更新，不是每次都批量拉。
- 为什么是 200 根：200 分钟 ≈ 3 小时 20 分，是"常驻内存、不用每次都打 Redis/ClickHouse"的一个够用
  缓冲，专门为实盘 500ms 时延预算设计的——1 分钟一次的高频场景，内存切片比打一次 ClickHouse 快得多。
- 范围很窄：只在 `interval="1m"` 生效。4h 这种"粗周期"完全不走这条路（见下）。

### 5.3 `lookback_bars`（`HistoricalPanelSource`/`LivePanelSource`）：ClickHouse 来源，含义因类而异

`HistoricalPanelSource.lookback_bars`（回测用，默认200）：不是"一次拉多少根"，是"往前多垫多少根"
——把请求区间的 `start_time` 往前推 `lookback_bars` 根，再从 ClickHouse 拉这个更早的起点到
`end_time` 的**整段区间**。目的是让回测**区间刚开始的头几根**就已经有完整的滚动窗口历史垫底，不用
从空窗口现攒。如果某个因子的最长窗口超过 `lookback_bars`，这个因子在区间起始的头
`(最长窗口 - lookback_bars)` 根会失败得很安全（`.rolling()` 数据不够时天然给 NaN，不是悄悄算错），
代价是这段时间没有信号，变相浪费一段评估区间——**是正确性/完整性问题，不只是效率**。

`LivePanelSource.lookback_bars`（实盘用，只服务 4h/1h/1d 这类"粗周期"，默认也是200）：这个才是真的
"每次现查最新 N 根"——每来一次粗周期的 `kline_ready` 通知，就对 ClickHouse 发一次
`LIMIT lookback_bars BY symbol` 的查询，重新拉一遍当前每个 symbol 最新的 N 根，**不做增量缓存**。
设计上就是故意不像 1m 那样维护常驻状态——4h/1h/1d 更新频率低得多（4 小时才触发一次），现查
ClickHouse 足够快，没必要为这么低频的场景再建一套增量状态机；`_build_coarse_event()` 走的正是这条
路，完全绕开 `WindowCache`。

### 5.4 一句话区分

`window_size` 是"1m 专属、Redis 来源、内存里增量维护的滑动窗口"；`lookback_bars` 是"ClickHouse
来源"，在回测里是"垫多少历史让起点不冷启动"，在实盘粗周期里是"每次现查多少根、不缓存"。

**行动项（留给阶段二再做，不是现在）**：真正开始写回测脚本时，`HistoricalPanelSource(lookback_bars=...)`
要设到不小于 §3 最终敲定的世坤因子最长窗口，否则回测区间起始那段会有因子信号缺失。

---

## 6. 代码位置速查表

| 参数 | 代码位置 | 状态 |
|---|---|---|
| `tradable_mask` 滚动窗口 | [`sherpa/metrics/tradability.py:18`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/tradability.py#L18) | ✅ 已改（120） |
| `tradable_mask` 冷启动缓冲 | [`sherpa/metrics/tradability.py:19`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/tradability.py#L19) | ✅ 已改（20） |
| Regime 四维度窗口 | [`sherpa/metrics/regime.py:26`](file:///d:/code-repo/Chomo/Sherpa/sherpa/metrics/regime.py#L26) | ✅ 已改（120，统一常量） |
| `regime_report()` 入口透传 | [`sherpa/backtest/regime_screening.py:34-36`](file:///d:/code-repo/Chomo/Sherpa/sherpa/backtest/regime_screening.py#L34-L36) | ✅ 已改（跟随统一常量） |
| Beta 滚动窗口 | [`sherpa/risk/exposure.py:14`](file:///d:/code-repo/Chomo/Sherpa/sherpa/risk/exposure.py#L14) | ✅ 已改（120） |
| Research 数据 `INTERVAL` ×3 | 见 §2 表格 | ✅ 已改（"4h"） |
| 世坤101因子内部窗口 | `sherpa/alpha/worldquant/{price_volume,momentum_reversal,microstructure,composite}/alphas.py` | ⏳ 待决策，见 §3 |
| Low-sample 阈值 ×2 | [`factor_orthogonalization/config.py:157-158`](file:///d:/code-repo/Chomo/Sherpa/research/factor_orthogonalization/config.py#L157-L158)、[`regime_factor_report.py:174-175`](file:///d:/code-repo/Chomo/Sherpa/research/regime_factor_report/regime_factor_report.py#L174-L175) | ⏳ 待决策，见 §4 |
| `HistoricalPanelSource.lookback_bars` | [`sherpa/data/panel_source.py:49`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L49) | 🔒 阶段二再处理，见 §5 |
| `LivePanelSource.lookback_bars`/`window_size` | [`sherpa/data/panel_source.py:114-115`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/panel_source.py#L114-L115) | 🔒 阶段三/四再处理，见 §5 |
