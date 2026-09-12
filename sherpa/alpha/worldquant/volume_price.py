"""量价关系类：用 volume 和 price 的联动/背离构造信号（设计文档 §6.3）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from .. import ops
from ..base import WorldQuantAlpha, register_alpha


@register_alpha
class Alpha002(WorldQuantAlpha):
    """Alpha#2：成交量变化率与当根K线实体涨跌幅的横截面负相关。

    (-1 * correlation(rank(delta(log(volume),2)), rank((close-open)/open), 6))
    """

    name = "alpha002"
    min_lookback = 8

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        part1 = ops.rank(ops.delta(ops.log(panel.volume), 2))
        part2 = ops.rank((panel.close - panel.open) / panel.open)
        return -1 * ops.ts_corr(part1, part2, 6)


@register_alpha
class Alpha003(WorldQuantAlpha):
    """Alpha#3：开盘价与成交量的横截面负相关。

    (-1 * correlation(rank(open), rank(volume), 10))
    """

    name = "alpha003"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_corr(ops.rank(panel.open), ops.rank(panel.volume), 10)


@register_alpha
class Alpha006(WorldQuantAlpha):
    """Alpha#6：开盘价与成交量的时序负相关（逐 symbol，不做横截面排名）。

    (-1 * correlation(open, volume, 10))
    """

    name = "alpha006"
    min_lookback = 10

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return -1 * ops.ts_corr(panel.open, panel.volume, 10)


@register_alpha
class Alpha012(WorldQuantAlpha):
    """Alpha#12：用成交量的变化方向作为价格反转的触发器。

    (sign(delta(volume,1)) * (-1 * delta(close,1)))
    """

    name = "alpha012"
    min_lookback = 2

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return ops.sign(ops.delta(panel.volume, 1)) * (-1 * ops.delta(panel.close, 1))
