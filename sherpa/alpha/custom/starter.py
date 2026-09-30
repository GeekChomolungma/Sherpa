"""自定义因子·starter 主题：两种写法的样例因子，同时是 custom 研究线的第一批因子。

`research/alpha_research/custom_starter/` 这条研究线（track）就是拿这个模块里的因子跑通
"阶段一体检 → 汇总报告"链路的。以后按交易经验写的新因子，按主题在 `sherpa/alpha/custom/`
下另开 `<主题>.py`，在 `custom/__init__.py` 里 import（下游关卡按 qualified_name 引用时
要能注册到），再给它开一条对应的 track。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ..base import CustomAlpha, custom_alpha, register_alpha


@custom_alpha("close_momentum_20", min_lookback=21)
def close_momentum_20(panel: BarPanel) -> pd.DataFrame:
    """函数式写法：适合"一个纯函数就是一个因子"的快速试验。"""
    return panel.close.pct_change(20)


@register_alpha
class VolumeSurge(CustomAlpha):
    """类写法：成交量相对 N 根均值的偏离度，适合需要构造参数/状态的场景。"""

    name = "volume_surge"

    def __init__(self, window: int = 20):
        super().__init__(window=window)
        self.name = f"volume_surge_{window}"
        self.min_lookback = window + 1

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        avg = panel.volume.rolling(self.params["window"]).mean()
        return panel.volume / avg - 1
