"""自定义因子·starter 主题：两种写法的样例因子，同时是 custom 研究线的第一批因子。

`research/alpha_research/custom_starter/` 这条研究线（track）就是拿这个模块里的因子跑通
"阶段一体检 → 汇总报告"链路的。以后按交易经验写的新因子，按主题在 `sherpa/alpha/custom/`
下另开 `<主题>.py`，在 `custom/__init__.py` 里 import（下游关卡按 qualified_name 引用时
要能注册到），再给它开一条对应的 track。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from .. import ops
from ..base import CustomAlpha, custom_alpha, register_alpha
from ..liquidity import LiquidityFilter, restrict


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


@register_alpha
class LiquidMomentumRank(CustomAlpha):
    """示意：带内部流动性范围的截面因子——N 根动量**只在流动性排前面的币之间**排名。

    演示 `sherpa.alpha.liquidity` 的用法，不追求因子本身有效。写法的顺序是关键：
    1. 时序部分（动量）在全量数据上算，不受范围影响——范围逐期变化，先盖掉再 rolling 会把序列弄断；
    2. `restrict` 把范围外的格子盖成 NaN；
    3. 截面部分（`ops.rank`）只在剩下的 symbol 之间比较，范围外的输出保持 NaN。

    `liquidity=LiquidityFilter()`（门槛全 0）时范围 = 全部有数据的 symbol，因子退化成普通的全截面动量排名。
    """

    name = "liquid_momentum_rank"

    def __init__(self, window: int = 20, liquidity: LiquidityFilter = LiquidityFilter(min_percentile=0.5)):
        super().__init__(window=window, liquidity=liquidity)
        self.min_lookback = max(window + 1, liquidity.min_lookback)

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        momentum = panel.close.pct_change(self.params["window"])  # 1. 时序：全量数据
        in_scope = self.params["liquidity"].mask(panel)
        return ops.rank(restrict(momentum, in_scope)) - 0.5        # 2+3. 圈范围后再截面排名
