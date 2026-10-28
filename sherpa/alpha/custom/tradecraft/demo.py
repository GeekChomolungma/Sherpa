"""示例：只用来打通 tradecraft 研究线的管道，**不是交易经验**。

规则是最朴素的短期反转（最近 1 天跌得多的看多、涨得多的看空），研究线跑通、可视化跟 V4 对比没问题之后，真正的交易经验
alpha 照这个文件的写法加进来。它留着当模板和管道的冒烟测试，不参与研究结论。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ...base import register_alpha
from . import indicators
from .base import TradecraftAlpha


@register_alpha
class TcDemoReversal(TradecraftAlpha):
    """最近 `window` 根（默认 6 根 = 1 天）涨跌幅取负：跌得越多分越高。"""

    name = "tc_demo_reversal"
    horizon_bars = 1
    window = 6
    lookback_bars = window + 1

    def score(self, panel: BarPanel) -> pd.DataFrame:
        return -indicators.returns(panel, self.window)
