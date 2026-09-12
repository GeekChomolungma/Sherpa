"""ATR（Average True Range）。"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel

from ..base import TradingViewIndicator, register_alpha


@register_alpha
class ATR(TradingViewIndicator):
    """True Range 的移动平均：max(high-low, |high-prev_close|, |low-prev_close|) 的 N 根均值。"""

    name = "atr"

    def __init__(self, period: int = 14):
        super().__init__(period=period)
        self.name = f"atr_{period}"
        self.min_lookback = period + 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        prev_close = panel.close.shift(1)
        true_range = np.maximum(
            np.maximum(panel.high - panel.low, (panel.high - prev_close).abs()),
            (panel.low - prev_close).abs(),
        )
        return true_range.rolling(self.params["period"]).mean()
