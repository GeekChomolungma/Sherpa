"""行业中性化占位基类（设计文档 §6.3 决策2）。

crypto 永续市场没有天然的"行业"分类维度，`BarPanel` 也没有这个字段。依赖 `indneutralize`/
`IndClass` 的世坤101公式全部继承这个基类：`compute()` 统一 `raise NotImplementedError`，不
拿代理维度（比如按上线时间/报价币种分组）硬凑——错的因子比没有因子更危险。这是以后真有
行业分类数据时的统一接入点：届时给 `BarPanel` 加一个 `group` 维度，再回来把这些公式填上。
"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import BarPanel

from ...base import WorldQuantAlpha


class IndustryNeutralPlaceholder(WorldQuantAlpha):
    """依赖 indneutralize/IndClass 的世坤101公式的公共占位基类，故意不用 @register_alpha 注册
    （这是抽象基类，不代表任何一个具体编号的 alpha）。"""

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.qualified_name} 依赖行业分类数据，当前 BarPanel 不支持（设计文档 §6.3）"
        )
