"""波动率类：用价格离散度/波动幅度构造信号（设计文档 §6.3）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from .. import ops
from ..base import WorldQuantAlpha, register_alpha


@register_alpha
class Alpha001(WorldQuantAlpha):
    """Alpha#1：下跌时用波动率、上涨时用收盘价，找窗口内极值出现的位置。

    (rank(Ts_ArgMax(SignedPower(((returns<0) ? stddev(returns,20) : close), 2), 5)) - 0.5)
    """

    name = "alpha001"
    min_lookback = 25  # 20（stddev窗口）+ 5（ts_argmax窗口）

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        returns = panel.close.pct_change()
        base = ops.stddev(returns, 20).where(returns < 0, panel.close)
        powered = ops.signed_power(base, 2)
        return ops.rank(ops.ts_argmax(powered, 5)) - 0.5
