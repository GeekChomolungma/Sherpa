"""反转/均值回归类：押注极端表现会被修正（设计文档 §6.3）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from .. import ops
from ..base import WorldQuantAlpha, register_alpha


@register_alpha
class Alpha004(WorldQuantAlpha):
    """Alpha#4：低价在横截面上持续偏低的 symbol 做反向。

    (-1 * Ts_Rank(rank(low), 9))
    """

    name = "alpha004"
    min_lookback = 9

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_rank(ops.rank(panel.low), 9)
