"""世坤101因子库：按经济含义分类到子模块，方便按方向挑选（设计文档 §6.3）。

已实现（一个经过核实的子集；101 篇公式全部核对工作量很大，没有把握的宁可先不写，
也不在交易系统里塞入没核实过的公式——错的因子比没有因子更危险）：

    momentum.py          动量类：押注趋势延续                    Alpha009
    reversal.py           反转/均值回归类：押注极端表现会被修正        Alpha004
    volume_price.py        量价关系类：volume 和 price 的联动/背离     Alpha002/003/006/012
    volatility.py          波动率类：用价格离散度构造信号            Alpha001
    pattern.py             价格形态类：K线内部结构/形状              Alpha101
    cross_sectional.py      跨截面/行业中性类：依赖 indneutralize/市值，暂不支持（占位）

新增一个因子：找到经济含义最接近的分类文件（没有合适的就新建一个），继承 WorldQuantAlpha，
用 @register_alpha 注册即可，不需要改这个 __init__ 或 AlphaEngine。
"""

from . import cross_sectional, momentum, pattern, reversal, volatility, volume_price
from .cross_sectional import IndustryNeutralPlaceholder
from .momentum import Alpha009
from .pattern import Alpha101
from .reversal import Alpha004
from .volatility import Alpha001
from .volume_price import Alpha002, Alpha003, Alpha006, Alpha012

__all__ = [
    "Alpha001",
    "Alpha002",
    "Alpha003",
    "Alpha004",
    "Alpha006",
    "Alpha009",
    "Alpha012",
    "Alpha101",
    "IndustryNeutralPlaceholder",
]
