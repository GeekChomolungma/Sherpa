# tradecraft：交易经验 alpha

把币圈手动交易的经验规则写成**截面打分**（每一期给每个币一个分数，越大越看多），走跟世坤因子、ML 模型同一条研究流水线，
再原样进回测和实盘。没有训练、没有模型文件：`BarPanel` 进，一张 `(T, N)` 打分出。

研究线：[`research/alpha_research/tradecraft/`](../../../../research/alpha_research/tradecraft/run_track.sh)。

```text
世坤        BarPanel ──公式──────────────────────────────→ (T, N) 打分
ML          BarPanel ──展开成 ABC 特征长表──模型推断──────→ (T, N) 打分
tradecraft  BarPanel ──指标（indicators.py）──交易规则────→ (T, N) 打分
```

---

## 1. 加一个新 alpha

**① 写类**：一个主题一个文件（比如 `breakout.py`），继承 `TradecraftAlpha`，参数全部写成类属性、放在类的开头：

```python
from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ...base import register_alpha
from . import indicators
from .base import TradecraftAlpha


@register_alpha
class TcBreakoutV1(TradecraftAlpha):
    """一句话说清交易逻辑：什么情况看多、什么情况看空、为什么（来自哪条经验）。"""

    name = "tc_breakout_v1"      # 必须 tc_ 开头；研究产出在 runs/tc_breakout_v1/
    horizon_bars = 1             # 持有期（根 bar）：这条经验预期多久兑现
    window = 42                  # 规则自己的参数
    surge = 2.0
    lookback_bars = window + 1   # 规则最长回看多少根（取最大的那个窗口）

    def score(self, panel: BarPanel) -> pd.DataFrame:
        near_high = indicators.dist_from_high(panel, self.window)          # 原始值，<= 0
        volume = indicators.volume_surge(panel, 6, self.window)
        return near_high.where(volume > self.surge)                          # 没放量 = NaN = 不参与
```

**② 注册**：在 `tradecraft/__init__.py` 里 import 它（import 才会触发 `@register_alpha`）。

**③ 单测自动覆盖**：`tests/alpha/test_tradecraft.py` 对每个注册的 tradecraft alpha 自动检查"不看未来"（截掉后面的数据，
前面的打分不变）、打分只在流动性范围内、参数声明合法。规则有需要精确核对的数值，再在那个文件里加专门的测试。

**④ 跑研究线**：

```bash
CH_HOST=... CH_PASSWORD=... bash research/alpha_research/tradecraft/run_track.sh --alphas custom.tc_breakout_v1
```

研究线最后还有一步**只做多回测**（步骤 6，`research/alpha_research/tradecraft/run_long_only.py`）：Top-K 只买不卖空、调仓每 2 / 3 根，跟等权基准比（只做多不是市场中性，要看跑没跑赢"闭眼买"），产出 `results*/long_only/`，画图加 `--book long_only`。

**⑤ 看结果、跟 V4 比**：读法同 `research/alpha_research/MLalpha/RESULT_READING.md`（RankIC 是主判据，04～06 只作确认）；画图：

```bash
python research/viz/viz.py run research/alpha_research/tradecraft/runs/tc_breakout_v1
python research/viz/viz.py compare research/alpha_research/MLalpha/runs/lgbm_v4 research/alpha_research/tradecraft/runs/tc_breakout_v1 --baseline lgbm_v4
```

**改参数 = 新版本**：下游按名字无参实例化，所以别改已经跑过的类的参数，写一个子类只改几个类属性，起新名字：

```python
@register_alpha
class TcBreakoutV2(TcBreakoutV1):
    name = "tc_breakout_v2"
    surge = 3.0
```

## 2. 打分约定

| 约定 | 为什么 |
| --- | --- |
| **越大越看多** | 关卡3 做多高分一端、做空低分一端；步骤 0 的 RankIC 按这个方向算，规则方向错了就是负数 |
| **NaN = 没观点、不参与**；0 = 中性 | NaN 不进当期排名、不会被 Top-K 选中，"看不清就不参与"在单个币上用它表达；0 照样参与排名、排在中间 |
| **尽量给连续强度** | 纯 +1 / 0 / −1 会大量并列，RankIC 被并列拉低，Top-K 在并列里怎么选也说不清。用"信号 × 强度" |
| **截面运算只在范围内做** | 先在全量数据上算时序（rolling），再 `self.rank_in_scope(raw, self.scope(panel))`；顺序反了时间序列会被范围打断 |
| **只用到第 t 根收盘为止的数据** | 单测自动守住。第 t 行的标签是 `close[t+1] → close[t+1+horizon]`（执行延迟 1 根），信号出来后紧接着那 4 小时不算 |
| **只做"选哪些币"** | 同一时刻给所有币相同值的择时规则（"BTC 走弱就少做"）截面上没有排序信息，RankIC 测不出来，关卡3 的多空组合也用不上。它属于 on_bar 里的叠加层。择时条件可以用来**调节**币之间的强弱 |

基类的 `compute()` 会把打分限制在流动性范围内（`TRADECRAFT_LIQUIDITY`：成交额排在当期前一半，跟 MLalpha 同一个口径，
等于研究线 `track.json` 的评估掩码，单测守住），子类不用自己处理。

## 3. 能用的数据

`BarPanel`（`sherpa/data/schema.py`）每个字段都是 `(T, N)` 宽表，行 = K 线起点（4h），列 = 币：

| 有 | 字段 |
| --- | --- |
| K 线 | `open` `high` `low` `close` `volume` `quote_volume`（USDT 成交额）`trades_count` |
| 主动买卖 | `taker_buy_volume` `taker_buy_quote_volume` |
| 合约持仓 | `open_interest`（及 `_high` / `_low`） |
| 多空比 | `long_short_ratio`（全市场账户）`top_account_long_short_ratio`（大户账户）`top_position_long_short_ratio`（大户持仓），各带 `_high` / `_low` |

**没有**：资金费率、订单簿深度、爆仓。规则要用到这些，得先在数据层（`sherpa/data/`）接入。

现成的指标在 `indicators.py`（全部是原始值、不排名）：涨跌幅、逐根波动、区间位置、离高点 / 低点的距离、K 线实体占比、
平均成交额、放量倍数、主动买占比、OI 变化率、OI 价值、多空比 z 分数。新指标先写在 alpha 里，确实被多个 alpha 用到再挪进来。

## 4. 方法上要注意的

- **样本外的含义变了**：规则没有训练，选择段（2023-01 ~ 2024-06）/ 验证段（~ 2026-03）的区别只在"规则和参数是在哪段数据上定下来的"。
  看完验证段的结果再改参数，验证段就不再是样本外；
- **经验本身可能来自验证段的行情**：交易经验是在 2024～2026 年的市场里攒出来的，等于"人脑看过答案"。所以对经验 alpha 来说，
  holdout（2026-03 ~ 2026-09）比验证段更重要，规则定稿后只跑一次；
- **会主动不参与（整期 NaN）的 alpha，04 表可能是空的**：关卡3 的 04 表剔除选择段空仓 > 20% 的组合（这条规则是给"币不够被迫空仓"
  设计的，ML / 世坤都靠它，不改），择时让整期空仓，常常 39 个组合全被剔掉。这种 alpha 看 `01_friction_summary.csv`（每个组合 ×
  成本 × 段的净 Sharpe、回撤、空仓比例，自己取中位数）、`02`、`06`（赚钱季度占比）和 `research/viz/` 的净值 / 回撤图；RankIC 看步骤 0；
- **持有期**：步骤 0 的 RankIC 主列按 `horizon_bars` 算，另外固定给 1 根、6 根两列。阶段一和关卡3 用的是 `research_config.json`
  的全局口径（1 根），跟默认值一致。跟 ML 模型（主指标 6 根）比 RankIC 时要用同一个持有期，`research/viz/` 的对比图会自动对齐。
