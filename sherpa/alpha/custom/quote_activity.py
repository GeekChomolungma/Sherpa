"""自定义因子·成交活跃度主题：按回溯窗口内的 USDT 成交额给 symbol 做截面活跃度排名。

对应研究线 `research/alpha_research/custom_quote_activity/`。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ..base import CustomAlpha, register_alpha


@register_alpha
class QuoteActivityRank(CustomAlpha):
    """回溯 `window` 根 bar 的累计成交额（`quote_volume`，USDT 计）在当期截面上的排名。

    **方向：值越小 = 越活跃**。成交额最大的 symbol 排第一，输出是百分位排名，值域 (0, 1]，最活跃的
    symbol 为 `1/N`、最不活跃的为 1。用百分位而不是名次，是因为 universe 大小逐期变化，名次在不同时期
    没有可比性；两者的截面顺序完全相同，Top-K 选出的 symbol 也一样。

    研究流水线不依赖这个方向约定：阶段一 IC 是秩相关，下游按 IC 的符号决定做多哪一端，所以"活跃的币
    跑赢"会体现为负 IC，关卡2/3 自动反过来做多排名靠前（值小）的一端。

    窗口没攒满（新上市、数据缺失）的格子是 NaN，不参与当期排名。
    """

    name = "quote_activity_rank"

    def __init__(self, window: int = 42):
        # 下游关卡按 qualified_name 无参实例化，研究里用的就是这里的默认值（4h 周期下 42 根 = 7 天）。
        super().__init__(window=window)
        self.min_lookback = window

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        window = self.params["window"]
        activity = panel.quote_volume.rolling(window, min_periods=window).sum()
        return activity.rank(axis=1, ascending=False, pct=True)
