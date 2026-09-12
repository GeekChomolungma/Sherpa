"""跨截面/行业中性类：世坤101里依赖 indneutralize / 市值(cap) 的公式（设计文档 §6.3）。

当前 BarPanel 没有行业分类字段、也没有市值字段——crypto 永续市场没有天然的"行业"维度，
这一类眼下没有任何具体因子实现。`IndustryNeutralPlaceholder` 只是给以后要接入这类公式的人
一个统一的失败方式和落点：不要为了"能跑"就拿一个凑出来的代理维度（比如随便按上线时间/
报价币种分组）去顶替行业分类，那样产出的因子值没有经济含义，比不实现更有害。

真要接的话：先有一份可信的行业/赛道分类数据源，再回来把 sherpa.data.schema.BarPanel
加一个 group 维度，然后这里的公式才有地方落。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ..base import WorldQuantAlpha


class IndustryNeutralPlaceholder(WorldQuantAlpha):
    """依赖 indneutralize/cap 的世坤101公式的公共占位基类，故意不用 @register_alpha 注册。"""

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.qualified_name} 依赖行业分类/市值数据，当前 BarPanel 不支持（设计文档 §6.3）"
        )
