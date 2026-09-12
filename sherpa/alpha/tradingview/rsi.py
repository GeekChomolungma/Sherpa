"""RSI（Relative Strength Index）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ..base import TradingViewIndicator, register_alpha


@register_alpha
class RSI(TradingViewIndicator):
    """经典 RSI：avg_gain / avg_loss 的相对强弱，值域 [0, 100]。"""

    name = "rsi"

    def __init__(self, period: int = 14):
        super().__init__(period=period)
        self.name = f"rsi_{period}"
        self.min_lookback = period + 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        period = self.params["period"]
        delta = panel.close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
