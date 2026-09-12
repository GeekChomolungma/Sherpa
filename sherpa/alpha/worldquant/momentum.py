"""动量类：押注价格趋势会延续（设计文档 §6.3）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from .. import ops
from ..base import WorldQuantAlpha, register_alpha


@register_alpha
class Alpha009(WorldQuantAlpha):
    """Alpha#9：连续同向变动时顺势延续，否则把当根变动反过来。

    ((0 < ts_min(delta(close,1),5)) ? delta(close,1) :
     ((ts_max(delta(close,1),5) < 0) ? delta(close,1) : (-1 * delta(close,1))))

    两个"顺势"分支（连续 5 根都在涨 / 连续 5 根都在跌）取值相同（都是 delta(close,1)），
    所以等价写成 "trending 时取 d，否则取 -d"。
    """

    name = "alpha009"
    min_lookback = 6

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        d = ops.delta(panel.close, 1)
        ts_min, ts_max = ops.ts_min(d, 5), ops.ts_max(d, 5)
        trending = (ts_min > 0) | (ts_max < 0)
        result = d.where(trending, -1 * d)
        # pandas 里 (NaN > 0) 直接算 False 而不是 NaN，5 根滚动窗口不满时 trending 会被
        # 悄悄判成 False，从而在 warmup 阶段冒出一个"看似正常"实则没有意义的数值——
        # 必须显式用 ts_min 的缺失情况把这部分重新盖成 NaN（呼应数据层"不悄悄补数据"的原则）。
        return result.where(ts_min.notna())
