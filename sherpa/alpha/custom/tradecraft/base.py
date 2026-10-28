"""交易经验 alpha（tradecraft）的基类：把币圈手动交易的经验规则写成截面打分。

跟世坤因子同一种形态——`BarPanel` 进、一张 `(T, N)` 打分出，没有训练、没有模型文件；跟 ML alpha 的区别是规则来自
交易经验而不是模型学习。研究线在 `research/alpha_research/tradecraft/`，写一个新 alpha 的步骤见同目录 README.md。

**子类只写 `score(panel)`**（规则本身），基类的 `compute()` 负责两件所有 tradecraft alpha 都必须一致的事：

1. **流动性范围**：打分只保留在 `liquidity`（默认 `TRADECRAFT_LIQUIDITY`）范围内的币，范围外是 NaN。跟研究线
   `track.json` 的外层掩码是同一套参数（单测守住），所以研究评估、回测、实盘看到的是同一批币；
2. **防看未来**：`score` 只能用到第 t 根 K 线收盘为止的数据。`tests/alpha/test_tradecraft.py` 对每个注册的
   tradecraft alpha 自动检查"截掉后面的数据，前面的打分不变"。

打分约定（研究流水线就是按这个解读的）：

- **数值越大越看多**：关卡3 做多高分一端、做空低分一端；
- **NaN = 没有观点、不参与**（不进当期排名，也不会被 Top-K 选中）；0 = 中性，照样参与排名、排在中间。
  "看不清就不参与"在单个币上就用 NaN 表达；
- **尽量给连续强度**：纯 +1 / 0 / −1 会有大量并列，RankIC 被并列拉低、Top-K 在并列里怎么选也说不清。
  用"信号 × 强度"（比如突破信号 × 突破幅度）；
- **截面运算只在范围内做**：先在全量数据上算时序（rolling 等），再 `restrict` 盖掉范围外，最后做截面排名
  （`self.rank_in_scope`），顺序反了时间序列会被范围打断；
- **只做"选哪些币"**：同一时刻给所有币相同值的择时规则（"BTC 走弱就少做"）截面上没有排序信息，不该写成 alpha，
  留给 on_bar 里的叠加层。择时条件可以用来**调节**币之间的强弱。

参数都写成类属性，放在类的开头：`horizon_bars`（持有期，默认 1 根 bar）、`lookback_bars`（规则最长回看多少根）和
规则自己的阈值 / 窗口。下游按 qualified_name 无参实例化，所以换参数 = 写一个子类（`XxxV2(XxxV1)` 只改几个类属性），
不同版本各有自己的名字和产出目录。
"""

from __future__ import annotations

from typing import ClassVar

import pandas as pd

from sherpa.data.schema import BarPanel
from sherpa.metrics.tradability import DEFAULT_LOOKBACK, SEASONING_PERIOD

from ...base import CustomAlpha
from ...liquidity import LiquidityFilter, restrict

NAME_PREFIX = "tc_"

# 默认流动性范围：成交额排在当期前一半的币（跟 MLalpha 同一个口径，结果能直接跟 V4 横比）。
# 必须等于 research/alpha_research/tradecraft/track.json 的 preprocess.tradable_mask（tests/research/test_tradecraft_track.py）。
TRADECRAFT_LIQUIDITY = LiquidityFilter(min_percentile=0.5, seasoning_period=SEASONING_PERIOD, lookback=DEFAULT_LOOKBACK)


class TradecraftAlpha(CustomAlpha):
    """交易经验 alpha 的基类。子类：设 `name`（`tc_` 开头）、参数类属性，实现 `score(panel)`，加 `@register_alpha`。"""

    name: ClassVar[str] = ""
    # 持有期（根 bar）：这个规则预期多久兑现。逐期 RankIC 时间线（步骤 0）按它算标签；阶段一 / 关卡3 用的是
    # research_config.json 的全局口径（1 根），默认值跟它一致
    horizon_bars: ClassVar[int] = 1
    # 规则本身最长回看多少根 bar（rolling 窗口、N 根涨幅之类取最大的那个），实盘取数据靠它
    lookback_bars: ClassVar[int] = 1
    liquidity: ClassVar[LiquidityFilter] = TRADECRAFT_LIQUIDITY

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            return  # 中间基类（还没起名字）不检查
        if not cls.name.startswith(NAME_PREFIX):
            raise ValueError(f"tradecraft alpha 的 name 必须以 {NAME_PREFIX!r} 开头：{cls.__name__}.name = {cls.name!r}")
        if not isinstance(cls.horizon_bars, int) or cls.horizon_bars < 1:
            raise ValueError(f"{cls.__name__}.horizon_bars 必须是 >= 1 的整数，收到 {cls.horizon_bars!r}")
        if not isinstance(cls.lookback_bars, int) or cls.lookback_bars < 1:
            raise ValueError(f"{cls.__name__}.lookback_bars 必须是 >= 1 的整数，收到 {cls.lookback_bars!r}")

    def __init__(self) -> None:
        super().__init__(horizon_bars=self.horizon_bars)

    @property
    def min_lookback(self) -> int:  # type: ignore[override]
        """规则本身的回看 + 流动性范围的回看（滚动成交额中位数、上线冷启动），取大的。"""
        return max(self.lookback_bars, self.liquidity.min_lookback)

    def scope(self, panel: BarPanel) -> pd.DataFrame:
        """`(T, N)` 布尔表：这一期这个币在不在流动性范围内。"""
        return self.liquidity.mask(panel)

    def rank_in_scope(self, raw: pd.DataFrame, scope: pd.DataFrame) -> pd.DataFrame:
        """只在范围内的币之间做截面百分位排名（0~1，越大越靠前），范围外是 NaN。`raw` 的时序部分要先在全量数据上算好。"""
        return restrict(raw, scope).rank(axis=1, pct=True)

    def score(self, panel: BarPanel) -> pd.DataFrame:
        """交易规则：`(T, N)` 打分，越大越看多，NaN = 不参与。子类实现。"""
        raise NotImplementedError

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        score = self.score(panel).reindex(index=panel.close.index, columns=panel.close.columns)
        return restrict(score.astype("float64"), self.scope(panel))
