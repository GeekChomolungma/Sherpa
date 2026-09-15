# WorldQuant 101 Formulaic Alphas 因子分类体系与工业级实现指南

> **论文参考**: Zura Kakushadze (2016), *101 Formulaic Alphas*, Quantigic Solutions LLC & Free University of Tbilisi, proprietary to WorldQuant LLC[cite: 1].
> **面向对象**: 本文档专为量化 Agent 编写因子计算引擎（如 `sherpa/alpha/factors.py`）提供**按金融语义分类归档**的规范说明。

---

## 一、 输入数据字段定义 (Input Data)

所有输入字段在 `sherpa/data/containers.py` 中以 `BarPanel`（`Time × Symbol` 的 2D DataFrame）组织[cite: 2]：

| 字段标识 | 中文定义 | 说明与工程防坑要点 |
| :--- | :--- | :--- |
| `returns` | 收盘收益率 | 每日 close-to-close 收益率：`(close - delay(close, 1)) / delay(close, 1)`[cite: 1] |
| `open` | 开盘价 | 每日/周期开盘价[cite: 1] |
| `close` | 收盘价 | 每日/周期收盘价[cite: 1] |
| `high` | 最高价 | 每日/周期最高价[cite: 1] |
| `low` | 最低价 | 每日/周期最低价[cite: 1] |
| `volume` | 成交量 | 标的成交股数/张数/币数[cite: 1] |
| `vwap` | 加权均价 | Volume-Weighted Average Price，无原生数据时用 `(H+L+C)/3` 代替[cite: 1] |
| `cap` | 总市值 | Market Capitalization，用于市值权重调整[cite: 1] |
| `adv{d}` | 日均成交金额 | 过去 d 天的平均每日成交金额（Dollar Volume）[cite: 1] |
| `IndClass` | 行业分类标识 | GICS/BICS/SIC 等分类层级（包含 `.sector`, `.industry`, `.subindustry`）[cite: 1] |

---

## 二、 基础算子语法约定 (Operators & Functions)

1. **浮点窗口下取整**：论文中形如 `ts_min(x, 16.1219)` 的非整数天数 `d`，在工程底层统一执行 `int(np.floor(d))`[cite: 1]。
2. **算子不区分大小写**：`ts_rank` 与 `Ts_Rank`、`sign` 与 `Sign` 具有相同语义[cite: 1]。

| 算子标识 | 类别 | 详细定义与数学实现[cite: 1] |
| :--- | :--- | :--- |
| `rank(x)` | 截面算子 | 截面百分比升序排名，映射至 `(0, 1]`[cite: 1] |
| `delay(x, d)` | 时序算子 | 序列滞后 d 期（即 $x_{t-d}$）[cite: 1] |
| `delta(x, d)` | 时序算子 | $x_t - x_{t-d}$[cite: 1] |
| `correlation(x, y, d)` | 时序算子 | 过去 d 期滚动皮尔逊相关系数[cite: 1] |
| `covariance(x, y, d)` | 时序算子 | 过去 d 期滚动协方差[cite: 1] |
| `scale(x, a=1)` | 截面算子 | 截面缩放：$x / \sum |x| \times a$（L1 归一化）[cite: 1] |
| `decay_linear(x, d)` | 时序算子 | 过去 d 期的线性衰减移动平均，权重为 $d, d-1, \dots, 1$[cite: 1] |
| `indneutralize(x, g)` | 截面算子 | 在行业分组 g 内做去均值（Demean）处理[cite: 1] |
| `ts_min` / `ts_max` | 时序算子 | 过去 d 期滑动最小值与最大值[cite: 1] |
| `ts_argmax` / `ts_argmin` | 时序算子 | 过去 d 期内极值出现日期的相对位置索引[cite: 1] |
| `ts_rank(x, d)` | 时序算子 | $x$ 在过去 d 期时序窗口内的百分比排名[cite: 1] |
| `SignedPower(x, a)` | 元素算子 | 保持符号的幂：$\text{sign}(x) \times (|x|^a)$[cite: 1] |

---

## 三、 分类因子公式归档 (Classified Alphas)

### 【分类一】行业与板块中性化类 (Industry & Sector Neutralization Alphas) —— 16 个
> **核心假说**：剥离宽基或行业贝塔（Beta）波动，通过在不同粒度的行业树（Sector, Industry, Subindustry）内部去均值，捕获纯特质 Alpha[cite: 1]。  
> *注：Alpha #48 为 Delay-0 因子[cite: 1]。无行业数据的市场（如加密货币），`indneutralize` 退化为截面全局去均值。*

| 编号 | 因子公式 (Formula)[cite: 1] | 中性化层级与特征[cite: 1] |
| :---: | :--- | :--- |
| **Alpha #48** | `(indneutralize(((correlation(delta(close, 1), delta(delay(close, 1), 1), 250) * delta(close, 1)) / close), IndClass.subindustry) / sum(((delta(close, 1) / delay(close, 1)) ^ 2), 250))` | **Delay-0**；子行业收益率自相关归一 |
| **Alpha #58** | `(-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.sector), volume, 3.92795), 7.89291), 5.50322))` | 板块级 VWAP 量能相关性衰减时序秩 |
| **Alpha #59** | `(-1 * Ts_Rank(decay_linear(correlation(IndNeutralize(((vwap * 0.728317) + (vwap * (1 - 0.728317))), IndClass.industry), volume, 4.25197), 16.2289), 8.19648))` | 行业级 VWAP 与成交量衰减时序秩 |
| **Alpha #63** | `((rank(decay_linear(delta(IndNeutralize(close, IndClass.industry), 2.25164), 8.22237)) - rank(decay_linear(correlation(((vwap * 0.318108) + (open * (1 - 0.318108))), sum(adv180, 37.2467), 13.557), 12.2883))) * -1)` | 行业中性差分衰减 vs 流动性衰减相关 |
| **Alpha #67** | `((rank((high - ts_min(high, 2.14593))) ^ rank(correlation(IndNeutralize(vwap, IndClass.sector), IndNeutralize(adv20, IndClass.subindustry), 6.02936))) * -1)` | 高点突破与板块/子行业跨级中性化相关 |
| **Alpha #69** | `((rank(ts_max(delta(IndNeutralize(vwap, IndClass.industry), 2.72412), 4.79344)) ^ Ts_Rank(correlation(((close * 0.490655) + (vwap * (1 - 0.490655))), adv20, 4.92416), 9.0615)) * -1)` | 行业中性 VWAP 加速度与加权流动性相关 |
| **Alpha #70** | `((rank(delta(vwap, 1.29456)) ^ Ts_Rank(correlation(IndNeutralize(close, IndClass.industry), adv50, 17.8256), 17.9171)) * -1)` | VWAP 差分与行业收盘流动性相关 |
| **Alpha #76** | `(max(rank(decay_linear(delta(vwap, 1.24383), 11.8259)), Ts_Rank(decay_linear(Ts_Rank(correlation(IndNeutralize(low, IndClass.sector), adv81, 8.14941), 19.569), 17.1543), 19.383)) * -1)` | 板块中性低价流动性相关与 VWAP 差分极值反转 |
| **Alpha #79** | `(rank(delta(IndNeutralize(((close * 0.60733) + (open * (1 - 0.60733))), IndClass.sector), 1.23438)) < rank(correlation(Ts_Rank(vwap, 3.60973), Ts_Rank(adv150, 9.18637), 14.6644)))` | 板块中性开收均价差分 vs VWAP 时序秩相关 |
| **Alpha #80** | `((rank(Sign(delta(IndNeutralize(((open * 0.868128) + (high * (1 - 0.868128))), IndClass.industry), 4.04545))) ^ Ts_Rank(correlation(high, adv10, 5.11456), 5.53756)) * -1)` | 行业中性价格差分符号与流动性相关幂运算 |
| **Alpha #82** | `(min(rank(decay_linear(delta(open, 1.46063), 14.8717)), Ts_Rank(decay_linear(correlation(IndNeutralize(volume, IndClass.sector), ((open * 0.634196) + (open * (1 - 0.634196))), 17.4842), 6.92131), 13.4283)) * -1)` | 板块中性成交量与开盘衰减极小值反转 |
| **Alpha #87** | `(max(rank(decay_linear(delta(((close * 0.369701) + (vwap * (1 - 0.369701))), 1.91233), 2.65461)), Ts_Rank(decay_linear(abs(correlation(IndNeutralize(adv81, IndClass.industry), close, 13.4132)), 4.89768), 14.4535)) * -1)` | 行业中性流动性绝对相关与均价速度极值 |
| **Alpha #89** | `(Ts_Rank(decay_linear(correlation(((low * 0.967285) + (low * (1 - 0.967285))), adv10, 6.94279), 5.51607), 3.79744) - Ts_Rank(decay_linear(delta(IndNeutralize(vwap, IndClass.industry), 3.48158), 10.1466), 15.3012))` | 流动性相关与行业中性 VWAP 差分对比 |
| **Alpha #90** | `((rank((close - ts_max(close, 4.66719))) ^ Ts_Rank(correlation(IndNeutralize(adv40, IndClass.subindustry), low, 5.38375), 3.21856)) * -1)` | 高点回撤与子行业中性流动性时序秩 |
| **Alpha #91** | `((Ts_Rank(decay_linear(decay_linear(correlation(IndNeutralize(close, IndClass.industry), volume, 9.74928), 16.398), 3.83219), 4.8667) - rank(decay_linear(correlation(vwap, adv30, 4.01303), 2.6809))) * -1)` | 行业中性收盘量能二阶平滑衰减相关 |
| **Alpha #93** | `(Ts_Rank(decay_linear(correlation(IndNeutralize(vwap, IndClass.industry), adv81, 17.4193), 19.848), 7.54455) / rank(decay_linear(delta(((close * 0.524434) + (vwap * (1 - 0.524434))), 2.77377), 16.2664)))` | 行业中性 VWAP 流动性与价格加速度商 |
| **Alpha #97** | `((rank(decay_linear(delta(IndNeutralize(((low * 0.721001) + (vwap * (1 - 0.721001))), IndClass.industry), 3.3705), 20.4523)) - Ts_Rank(decay_linear(Ts_Rank(correlation(Ts_Rank(low, 7.87871), Ts_Rank(adv60, 17.255), 4.97547), 18.5925), 15.7152), 6.71659)) * -1)` | 行业中性均价速度与多重时序秩相关衰减 |
| **Alpha #100** | `(0 - (1 * (((1.5 * scale(indneutralize(indneutralize(rank(((((close - low) - (high - close)) / (high - low)) * volume)), IndClass.subindustry), IndClass.subindustry))) - scale(indneutralize((correlation(close, rank(adv20), 5) - rank(ts_argmin(close, 30))), IndClass.subindustry))) * (volume / adv20))))` | 双重子行业中性化日内资金流向与流动性压力 |

---

### 【分类二】量价关系与流动性交叉类 (Price-Volume & Liquidity Interaction Alphas) —— 28 个
> **核心假说**：价格是由资金量驱动的。通过时序/截面上的量价相关性（Correlation）、协方差（Covariance）及成交金额加权，捕捉主力吸筹、量价背离与流动性溢价[cite: 1]。

| 编号 | 因子公式 (Formula)[cite: 1] | 核心机制[cite: 1] |
| :---: | :--- | :--- |
| **Alpha #2** | `(-1 * correlation(rank(delta(log(volume), 2)), rank(((close - open) / open)), 6))` | 成交量对数加速度与日内收益率秩负相关 |
| **Alpha #3** | `(-1 * correlation(rank(open), rank(volume), 10))` | 开盘价与成交量截面排名负相关 |
| **Alpha #6** | `(-1 * correlation(open, volume, 10))` | 开盘价与成交量时序相关性反转 |
| **Alpha #11** | `((rank(ts_max((vwap - close), 3)) + rank(ts_min((vwap - close), 3))) * rank(delta(volume, 3)))` | VWAP 极值离差与放量突增乘积 |
| **Alpha #12** | `(sign(delta(volume, 1)) * (-1 * delta(close, 1)))` | 单日放量滞涨与缩量下跌反转 |
| **Alpha #13** | `(-1 * rank(covariance(rank(close), rank(volume), 5)))` | 收盘价与成交量排名协方差反转 |
| **Alpha #14** | `((-1 * rank(delta(returns, 3))) * correlation(open, volume, 10))` | 收益率加速度与开盘量价相关交叉 |
| **Alpha #15** | `(-1 * sum(rank(correlation(rank(high), rank(volume), 3)), 3))` | 高点成交量秩相关累加反转 |
| **Alpha #16** | `(-1 * rank(covariance(rank(high), rank(volume), 5)))` | 最高价与成交量排名协方差反转 |
| **Alpha #17** | `(((-1 * rank(ts_rank(close, 10))) * rank(delta(delta(close, 1), 1))) * rank(ts_rank((volume / adv20), 5)))` | 价格二阶导与异常成交量冲击 |
| **Alpha #22** | `(-1 * (delta(correlation(high, volume, 5), 5) * rank(stddev(close, 20))))` | 量价相关性动量变化与波动率加权 |
| **Alpha #25** | `rank(((((-1 * returns) * adv20) * vwap) * (high - close)))` | 跌幅、上影线与流动性规模综合打分 |
| **Alpha #27** | `((0.5 < rank((sum(correlation(rank(volume), rank(vwap), 6), 2) / 2.0))) ? (-1 * 1) : 1)` | VWAP 与成交量秩相关均值阈值反转 |
| **Alpha #30** | `(((1.0 - rank(((sign((close - delay(close, 1))) + sign((delay(close, 1) - delay(close, 2)))) + sign((delay(close, 2) - delay(close, 3)))))) * sum(volume, 5)) / sum(volume, 20))` | 连涨连跌持续性反转，短期成交量加权 |
| **Alpha #35** | `((Ts_Rank(volume, 32) * (1 - Ts_Rank(((close + high) - low), 16))) * (1 - Ts_Rank(returns, 32)))` | 主力吸筹模式（放量 + 窄幅震荡 + 低收益） |
| **Alpha #39** | `((-1 * rank((delta(close, 7) * (1 - rank(decay_linear((volume / adv20), 9)))))) * (1 + rank(sum(returns, 250))))` | 缩量假突破反转与长周期动量增强 |
| **Alpha #40** | `((-1 * rank(stddev(high, 10))) * correlation(high, volume, 10))` | 高点波动率与量价相关性乘积 |
| **Alpha #43** | `(ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))` | 异常成交量比持续性与下跌动量衰减 |
| **Alpha #44** | `(-1 * correlation(high, rank(volume), 5))` | 最高价与成交量秩负相关 |
| **Alpha #45** | `(-1 * ((rank((sum(delay(close, 5), 20) / 20)) * correlation(close, volume, 2)) * rank(correlation(sum(close, 5), sum(close, 20), 2))))` | 均线时序相关与短期量价相关乘积 |
| **Alpha #50** | `(-1 * ts_max(rank(correlation(rank(volume), rank(vwap), 5)), 5))` | 滚动最大 VWAP-成交量秩相关反转 |
| **Alpha #56** | `(0 - (1 * (rank((sum(returns, 10) / sum(sum(returns, 2), 3))) * rank((returns * cap)))))` | 收益率累加比值与市值-收益冲击反转 |
| **Alpha #61** | `(rank((vwap - ts_min(vwap, 16.1219))) < rank(correlation(vwap, adv180, 17.9282)))` | VWAP 触底程度 vs 长期流动性相关比较 |
| **Alpha #62** | `((rank(correlation(vwap, sum(adv20, 22.4101), 9.91009)) < rank(((rank(open) + rank(open)) < (rank(((high + low) / 2)) + rank(high))))) * -1)` | 流动性相关 vs 开盘中枢偏离布尔对抗 |
| **Alpha #64** | `((rank(correlation(sum(((open * 0.178404) + (low * (1 - 0.178404))), 12.7054), sum(adv120, 12.7054), 16.6208)) < rank(delta(((((high + low) / 2) * 0.178404) + (vwap * (1 - 0.178404))), 3.69741))) * -1)` | 加权低点流动性相关 vs 均价速度比较 |
| **Alpha #74** | `((rank(correlation(close, sum(adv30, 37.4843), 15.1365)) < rank(correlation(rank(((high * 0.0261661) + (vwap * (1 - 0.0261661)))), rank(volume), 11.4791))) * -1)` | 收盘流动性相关 vs 均价成交量秩相关 |
| **Alpha #75** | `(rank(correlation(vwap, volume, 4.24304)) < rank(correlation(rank(low), rank(adv50), 12.4413)))` | VWAP 量能相关 vs 低点流动性秩相关 |
| **Alpha #78** | `(rank(correlation(sum(((low * 0.352233) + (vwap * (1 - 0.352233))), 19.7428), sum(adv40, 19.7428), 6.83313)) ^ rank(correlation(rank(vwap), rank(volume), 5.77492)))` | 低价流动性相关与 VWAP 量能秩相关幂运算 |

---

### 【分类三】动量与趋势反转类 (Momentum, Mean-Reversion & Gap Alphas) —— 25 个
> **核心假说**：资产价格具有短期过度反应（Overreaction）导致的均值回归特性，或中期惯性形成的动量趋势[cite: 1]。

| 编号 | 因子公式 (Formula)[cite: 1] | 核心机制[cite: 1] |
| :---: | :--- | :--- |
| **Alpha #4** | `(-1 * Ts_Rank(rank(low), 9))` | 最低价截面排名的时序排位反转 |
| **Alpha #7** | `((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : (-1 * 1))` | 放量期 7 日价格动量时序反转 |
| **Alpha #8** | `(-1 * rank(((sum(open, 5) * sum(returns, 5)) - delay((sum(open, 5) * sum(returns, 5)), 10))))` | 开盘价与收益率乘积的差分反转 |
| **Alpha #9** | `((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))` | 5 日连续涨跌突破趋势跟随与震荡反转 |
| **Alpha #10** | `rank(((0 < ts_min(delta(close, 1), 4)) ? delta(close, 1) : ((ts_max(delta(close, 1), 4) < 0) ? delta(close, 1) : (-1 * delta(close, 1)))))` | 4 日连续趋势突破状态机截面排序 |
| **Alpha #19** | `((-1 * sign(((close - delay(close, 7)) + delta(close, 7)))) * (1 + rank((1 + sum(returns, 250)))))` | 短期 7 日差分反转受 250 日长动量加权 |
| **Alpha #20** | `(((-1 * rank((open - delay(high, 1)))) * rank((open - delay(close, 1)))) * rank((open - delay(low, 1))))` | 昨日高开低三点跳空缺口复合反转 |
| **Alpha #21** | `((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) : (((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 : (((1 < (volume / adv20)) \|\| ((volume / adv20) == 1)) ? 1 : (-1 * 1))))` | 布林带通道突破与量能过滤状态机 |
| **Alpha #23** | `(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)` | 突破 20 日高价均线压制反转 |
| **Alpha #24** | `((((delta((sum(close, 100) / 100), 100) / delay(close, 100)) < 0.05) \|\| ((delta((sum(close, 100) / 100), 100) / delay(close, 100)) == 0.05)) ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3)))` | 百日趋势平缓期触底反弹 vs 短期差分 |
| **Alpha #31** | `((rank(rank(rank(decay_linear((-1 * rank(rank(delta(close, 10)))), 10)))) + rank((-1 * delta(close, 3)))) + sign(scale(correlation(adv20, low, 12))))` | 平滑衰减差分与短期反转复合 |
| **Alpha #32** | `(scale(((sum(close, 7) / 7) - close)) + (20 * scale(correlation(vwap, delay(close, 5), 230))))` | 7 日均线回归 + 长期跨期相关 |
| **Alpha #33** | `rank((-1 * ((1 - (open / close)) ^ 1)))` | 日内收盘开盘比率强反转 |
| **Alpha #34** | `rank(((1 - rank((stddev(returns, 2) / stddev(returns, 5)))) + (1 - rank(delta(close, 1)))))` | 短期波动率压缩与单日差分反转 |
| **Alpha #37** | `(rank(correlation(delay((open - close), 1), close, 200)) + rank((open - close)))` | 滞后日内差价长期相关与当日差价 |
| **Alpha #38** | `((-1 * rank(Ts_Rank(close, 10))) * rank((close / open)))` | 创 10 日新高位与日内强势综合反转 |
| **Alpha #46** | `((0.25 < (((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10))) ? (-1 * 1) : (((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < 0) ? 1 : ((-1 * 1) * (close - delay(close, 1)))))` | 二阶价格加速度三段式状态机 |
| **Alpha #49** | `(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.1)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))` | 急剧减速段阈值反转 |
| **Alpha #51** | `(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.05)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))` | 微幅减速段阈值反转 |
| **Alpha #52** | `((((-1 * ts_min(low, 5)) + delay(ts_min(low, 5), 5)) * rank(((sum(returns, 240) - sum(returns, 20)) / 220))) * ts_rank(volume, 5))` | 支撑位下移与长周期动量增强 |
| **Alpha #86** | `((Ts_Rank(correlation(close, sum(adv20, 14.7444), 6.00049), 20.4195) < rank(((open + close) - (vwap + open)))) * -1)` | 流动性相关时序秩 vs 日内均价偏离 |
| **Alpha #88** | `min(rank(decay_linear(((rank(open) + rank(low)) - (rank(high) + rank(close))), 8.06882)), Ts_Rank(decay_linear(correlation(Ts_Rank(close, 8.44728), Ts_Rank(adv60, 20.6966), 8.01266), 6.65053), 2.61957))` | 四价秩差分衰减与流动性相关极小值 |
| **Alpha #95** | `(rank((open - ts_min(open, 12.4105))) < Ts_Rank((rank(correlation(sum(((high + low) / 2), 19.1351), sum(adv40, 19.1351), 12.8742)) ^ 5), 11.7584))` | 开盘突破低点 vs 均价流动性秩时序排位 |
| **Alpha #99** | `((rank(correlation(sum(((high + low) / 2), 19.8975), sum(adv60, 19.8975), 8.8136)) < rank(correlation(low, volume, 6.28259))) * -1)` | 中轴流动性相关 vs 最低价量能相关比较 |
| **Alpha #101** | `((close - open) / ((high - low) + 0.001))` | **Delay-1**；经典日内 K 线实体动量 |

---

### 【分类四】高低价差与盘口结构类 (Intraday Microstructure & Range Volatility Alphas) —— 18 个
> **核心假说**：单日 K 线内部包含丰富的买卖压力博弈信息，通过最高价、最低价、收盘价与 VWAP 之间的几何偏离（影线、多空相对力量），量化买卖双方的竭竭状态[cite: 1]。  
> *注：Alpha #42, #53, #54 为 Delay-0 因子[cite: 1]。*

| 编号 | 因子公式 (Formula)[cite: 1] | 核心机制[cite: 1] |
| :---: | :--- | :--- |
| **Alpha #5** | `(rank((open - (sum(vwap, 10) / 10))) * (-1 * abs(rank((close - vwap)))))` | 开盘偏离 VWAP 均线与日内偏离绝对值 |
| **Alpha #18** | `(-1 * rank(((stddev(abs((close - open)), 5) + (close - open)) + correlation(close, open, 10))))` | 日内实体振幅标准差与开收价差综合反转 |
| **Alpha #28** | `scale(((correlation(adv20, low, 5) + ((high + low) / 2)) - close))` | 流动性相关加权的中枢价与收盘价差 |
| **Alpha #41** | `(((high * low) ^ 0.5) - vwap)` | 高低几何均价对 VWAP 偏离度 |
| **Alpha #42** | `(rank((vwap - close)) / rank((vwap + close)))` | **Delay-0**；日内 VWAP 均值回归 |
| **Alpha #47** | `((((rank((1 / close)) * volume) / adv20) * ((high * rank((high - close))) / (sum(high, 5) / 5))) - rank((vwap - delay(vwap, 5))))` | 低价股放量、上影线打压与 VWAP 动量 |
| **Alpha #53** | `(-1 * delta((((close - low) - (high - close)) / (close - low)), 9))` | **Delay-0**；盘口买卖力量比率差分反转 |
| **Alpha #54** | `((-1 * ((low - close) * (open ^ 5))) / ((low - high) * (close ^ 5)))` | **Delay-0**；高阶非线性开收高低价偏离 |
| **Alpha #55** | `(-1 * correlation(rank(((close - ts_min(low, 12)) / (ts_max(high, 12) - ts_min(low, 12)))), rank(volume), 6))` | KDJ/Stochastics 随机指标与量能秩负相关 |
| **Alpha #57** | `(0 - (1 * ((close - vwap) / decay_linear(rank(ts_argmax(close, 30)), 2))))` | 收盘与 VWAP 差值受最高价发生日衰减抑制 |
| **Alpha #60** | `(0 - (1 * ((2 * scale(rank(((((close - low) - (high - close)) / (high - low)) * volume)))) - scale(rank(ts_argmax(close, 10))))))` | 资金流向与最高点发生日截面博弈 |
| **Alpha #65** | `((rank(correlation(((open * 0.00817205) + (vwap * (1 - 0.00817205))), sum(adv60, 8.6911), 6.40374)) < rank((open - ts_min(open, 13.635)))) * -1)` | VWAP 流动性相关 vs 开盘触底程度 |
| **Alpha #66** | `((rank(decay_linear(delta(vwap, 3.51013), 7.23052)) + Ts_Rank(decay_linear(((((low * 0.96633) + (low * (1 - 0.96633))) - vwap) / (open - ((high + low) / 2))), 11.4157), 6.72611)) * -1)` | VWAP 差分衰减与日内振幅中枢偏离衰减 |
| **Alpha #68** | `((Ts_Rank(correlation(rank(high), rank(adv15), 8.91644), 13.9333) < rank(delta(((close * 0.518371) + (low * (1 - 0.518371))), 1.06157))) * -1)` | 高点流动性相关时序秩 vs 加权价格差分 |
| **Alpha #73** | `(max(rank(decay_linear(delta(vwap, 4.72775), 2.91864)), Ts_Rank(decay_linear(((delta(((open * 0.147155) + (low * (1 - 0.147155))), 2.03608) / ((open * 0.147155) + (low * (1 - 0.147155)))) * -1), 3.33829), 16.7411)) * -1)` | VWAP 差分与开盘低点加权跌幅极值 |
| **Alpha #77** | `min(rank(decay_linear(((((high + low) / 2) + high) - (vwap + high)), 20.0451)), rank(decay_linear(correlation(((high + low) / 2), adv40, 3.1614), 5.64125)))` | 中轴偏离 VWAP 衰减与流动性相关衰减极小值 |
| **Alpha #83** | `((rank(delay(((high - low) / (sum(close, 5) / 5)), 2)) * rank(rank(volume))) / (((high - low) / (sum(close, 5) / 5)) / (vwap - close)))` | 振幅比率滞后与日内 VWAP 偏离微观结构 |
| **Alpha #92** | `min(Ts_Rank(decay_linear(((((high + low) / 2) + close) < (low + open)), 14.7221), 18.8683), Ts_Rank(decay_linear(correlation(rank(low), rank(adv30), 7.58555), 6.94024), 6.80584))` | 日内重心低位布尔衰减与流动性时序秩 |

---

### 【分类五】复合极值与非线性时序衰减类 (Composite Non-linear & Time-Series Extreme Alphas) —— 14 个
> **核心假说**：近期的信息权重高于远期（加权线性衰减），同时形态拐点（如破位极值发生日）具有强烈的前瞻指示能力；采用符号幂变换增加极端多空标的得分差异[cite: 1]。

| 编号 | 因子公式 (Formula)[cite: 1] | 核心机制[cite: 1] |
| :---: | :--- | :--- |
| **Alpha #1** | `(rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)` | 条件收益极值发生日时序秩与符号幂 |
| **Alpha #26** | `(-1 * ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))` | 量能与高点时序秩相关极大值反转 |
| **Alpha #29** | `(min(product(rank(rank(scale(log(sum(ts_min(rank(rank((-1 * rank(delta((close - 1), 5))))), 2), 1))))), 1), 5) + ts_rank(delay((-1 * returns), 6), 5))` | 深度嵌套多重截面秩与对数连乘极值复合 |
| **Alpha #36** | `(((((2.21 * rank(correlation((close - open), delay(volume, 1), 15))) + (0.7 * rank((open - close)))) + (0.73 * rank(Ts_Rank(delay((-1 * returns), 6), 5)))) + rank(abs(correlation(vwap, adv20, 6)))) + (0.6 * rank((((sum(close, 200) / 200) - open) * (close - open)))))` | 经典多因子经验回归加权线性集成 |
| **Alpha #71** | `max(Ts_Rank(decay_linear(correlation(Ts_Rank(close, 3.43976), Ts_Rank(adv180, 12.0647), 18.0175), 4.20501), 15.6948), Ts_Rank(decay_linear((rank(((low + open) - (vwap + vwap))) ^ 2), 16.4662), 4.4388))` | 收盘流动性衰减时序秩与均价偏离平方极值 |
| **Alpha #72** | `(rank(decay_linear(correlation(((high + low) / 2), adv40, 8.93345), 10.1519)) / rank(decay_linear(correlation(Ts_Rank(vwap, 3.72469), Ts_Rank(volume, 18.5188), 6.86671), 2.95011)))` | 中轴流动性衰减相关 vs VWAP 衰减量秩商 |
| **Alpha #81** | `((rank(Log(product(rank((rank(correlation(vwap, sum(adv10, 49.6054), 8.47743)) ^ 4)), 14.9655))) < rank(correlation(rank(vwap), rank(volume), 5.07914))) * -1)` | 流动性相关 4 次方连乘对数截面秩比较 |
| **Alpha #84** | `SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))` | VWAP 新高离差时序秩的收益差分符号幂 |
| **Alpha #85** | `(rank(correlation(((high * 0.876703) + (close * (1 - 0.876703))), adv30, 9.61331)) ^ rank(correlation(Ts_Rank(((high + low) / 2), 3.70596), Ts_Rank(volume, 10.1595), 7.11408)))` | 高收加权流动性相关秩与中轴量秩相关幂运算 |
| **Alpha #94** | `((rank((vwap - ts_min(vwap, 11.5783))) ^ Ts_Rank(correlation(Ts_Rank(vwap, 19.6462), Ts_Rank(adv60, 4.02992), 18.0926), 2.70756)) * -1)` | VWAP 低点离差秩与流动性时序秩幂反转 |
| **Alpha #96** | `(max(Ts_Rank(decay_linear(correlation(rank(vwap), rank(volume), 3.83878), 4.16783), 8.38151), Ts_Rank(decay_linear(Ts_ArgMax(correlation(Ts_Rank(close, 7.45404), Ts_Rank(adv60, 4.13242), 3.65459), 12.6556), 14.0365), 13.4143)) * -1)` | VWAP 量秩衰减与极值日时序秩最大值反转 |
| **Alpha #98** | `(rank(decay_linear(correlation(vwap, sum(adv5, 26.4719), 4.58418), 7.18088)) - rank(decay_linear(Ts_Rank(Ts_ArgMin(correlation(rank(open), rank(adv15), 20.8187), 8.62571), 6.95668), 8.07206)))` | VWAP 短期流动性相关衰减 vs 极小日时序秩衰减 |

---

## 四、 后续 Agent 编码工程指引 (Agent Implementation)

1. **子模块目录划分**：建议在 `sherpa/alpha/` 目录下拆分成 5 个文件（如 `industry.py`, `price_volume.py`, `momentum.py`, `microstructure.py`, `composite.py`），通过统一的 `__init__.py` 暴露[cite: 2]。
2. **防除零保护机制**：对于 Alpha #53, #54, #83, #101 等涉及分母的公式，在实现时须对分母增加 `eps = 1e-7` 或在 `high == low` 时返回 NaN，防止生成无穷大值[cite: 1]。
3. **时序未来函数防御**：
   * **Delay-0 因子**（Alpha #42, #48, #53, #54）在回测时仅能在 `t` 日 Close 前撮合[cite: 1]；
   * **Delay-1 因子**（其余 97 个因子）在生成持仓权重矩阵后，**必须强制执行 `exec_weights = weights.shift(1)`**[cite: 1, 3]，在下一期 Open 进行交易执行[cite: 3]。