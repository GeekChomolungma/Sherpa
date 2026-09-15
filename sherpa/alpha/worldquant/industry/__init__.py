"""分类一·行业与板块中性化类（18 个，`101_alpha_factors_classified.md` §一）。

全部依赖 `indneutralize`/`IndClass`，`BarPanel` 没有行业分类字段，v1 统一占位不实现——
详见 `base.IndustryNeutralPlaceholder` 和设计文档 §6.3 决策2。
"""

from .base import IndustryNeutralPlaceholder
from .placeholders import (
    Alpha048,
    Alpha058,
    Alpha059,
    Alpha063,
    Alpha067,
    Alpha069,
    Alpha070,
    Alpha076,
    Alpha079,
    Alpha080,
    Alpha082,
    Alpha087,
    Alpha089,
    Alpha090,
    Alpha091,
    Alpha093,
    Alpha097,
    Alpha100,
)

__all__ = [
    "IndustryNeutralPlaceholder",
    "Alpha048",
    "Alpha058",
    "Alpha059",
    "Alpha063",
    "Alpha067",
    "Alpha069",
    "Alpha070",
    "Alpha076",
    "Alpha079",
    "Alpha080",
    "Alpha082",
    "Alpha087",
    "Alpha089",
    "Alpha090",
    "Alpha091",
    "Alpha093",
    "Alpha097",
    "Alpha100",
]
