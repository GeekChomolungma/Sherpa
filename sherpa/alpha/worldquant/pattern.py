"""价格形态类：不直接用涨跌幅，而是描述K线内部结构/形状（设计文档 §6.3）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ..base import WorldQuantAlpha, register_alpha


@register_alpha
class Alpha101(WorldQuantAlpha):
    """Alpha#101：当根K线实体涨跌幅相对振幅的占比——经典"收盘强弱"形态因子。

    ((close - open) / ((high - low) + .001))
    """

    name = "alpha101"
    min_lookback = 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return (panel.close - panel.open) / ((panel.high - panel.low) + 0.001)
