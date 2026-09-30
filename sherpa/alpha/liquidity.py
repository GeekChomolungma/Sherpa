"""因子内部的流动性范围：让因子公式里的**截面运算**只在"真的有流动性"的 symbol 里做。

跟研究流水线的外层掩码（`sherpa.backtest.residual.ScorePreprocessor` 里的 `tradable_mask`）是两回事：

- **外层掩码**：因子先在全截面上算完，再把不可交易的 symbol 盖成 NaN——决定"哪些分数参与评估 / 交易"；
- **内层范围（这里）**：因子公式自己的一部分。`rank()`、截面 zscore 这类运算如果把死币也算进去，活跃币的
  分位数会被整体挤偏（比如 500 个币里只有 150 个活跃，活跃币的 rank 全挤在某一段）。交易经验里"只在主流币
  之间比较"的因子，应该在公式里先圈定范围再做截面运算。

两层互不替代：外层掩码研究线统一加，内层范围由因子作者按公式需要决定用不用、门槛多少。

**门槛全为 0 = 不限制**：`LiquidityFilter()`（默认值）返回"当期有数据的全部 symbol"，等价于没有这层范围，
因子退回全截面计算。注意不能直接拿 `tradable_mask` 传 0 门槛来实现这个语义——它的滚动窗口 warm-up 和冷启动
缓冲仍然会把早期数据掩掉。

判定逻辑复用 `sherpa.metrics.tradability.tradable_mask`（只看成交额 / 成交笔数，不看价格和收益，不会前视），
不另起一套口径。

接口现在只有最小的两件事：`LiquidityFilter.mask(panel)` 圈范围、`restrict(x, mask)` 把范围外的格子盖掉。
更完整的"范围内截面算子"（带范围的 zscore、分组中性化等）等真正写到需要的因子时再加。
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from sherpa.data.schema import BarPanel
from sherpa.metrics.tradability import DEFAULT_LOOKBACK, tradable_mask


@dataclass(frozen=True)
class LiquidityFilter:
    """因子内部截面运算的流动性范围。字段含义同 `tradable_mask` 的同名参数，默认全部为 0（不限制）。

    - `min_percentile`：滚动成交额中位数在当期截面的百分位下限（0.5 = 只留成交额排前一半的币）；
    - `min_quote_volume` / `min_trades_count`：滚动中位数的绝对地板（USDT / 笔）；
    - `seasoning_period`：上线后前 N 根 bar 不算；
    - `lookback`：滚动中位数窗口，只在有任一门槛生效时才用得到。

    frozen dataclass：可以直接当因子的构造参数、进 `Alpha.params`，也能 pickle 给多进程 worker。
    """

    min_percentile: float = 0.0
    min_quote_volume: float = 0.0
    min_trades_count: float = 0.0
    seasoning_period: int = 0
    lookback: int = DEFAULT_LOOKBACK

    @property
    def enabled(self) -> bool:
        return any(v > 0 for v in (self.min_percentile, self.min_quote_volume, self.min_trades_count, self.seasoning_period))

    @property
    def min_lookback(self) -> int:
        """这层范围本身需要的回看根数（给因子的 `min_lookback` 取 max 用）；不限制时是 1。"""
        return max(self.lookback, self.seasoning_period + 1) if self.enabled else 1

    def mask(self, panel: BarPanel) -> pd.DataFrame:
        """`(T, N)` 布尔矩阵：True = 这一期这个 symbol 在范围内。不限制时 = 当期有收盘价的全部 symbol。"""
        if not self.enabled:
            return panel.close.notna()
        return tradable_mask(
            panel.quote_volume,
            panel.trades_count,
            lookback=self.lookback,
            min_percentile=self.min_percentile,
            min_quote_volume=self.min_quote_volume,
            min_trades_count=self.min_trades_count,
            seasoning_period=self.seasoning_period,
        )


def restrict(x: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """把范围外的格子盖成 NaN。截面运算（`ops.rank` 等）对 NaN 逐期跳过，所以先 `restrict` 再做截面运算，
    就等于"只在范围内的 symbol 之间比较"。时序运算（rolling 等）不要在 `restrict` 之后做——范围是逐期变化的，
    盖掉之后时间序列会断。正确顺序：先在全量数据上算时序部分，再 `restrict`，最后做截面部分。
    """
    return x.where(mask.reindex(index=x.index, columns=x.columns, fill_value=False))
