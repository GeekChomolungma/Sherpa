"""自定义因子写法示例（设计文档 §6.3）。

真实的用户自定义因子建议放在策略作者自己的仓库/脚本里，import sherpa.alpha.base 的
CustomAlpha/custom_alpha 就够用，不需要依赖这个模块——这里只演示两种写法。
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
