"""自定义因子家族（设计文档 §6.3）：继承 CustomAlpha 写类，或用 @custom_alpha 装饰函数。

按主题分模块（`starter.py`, `quote_activity.py`, `ml/`, ...）。每个主题模块都要在这里 import：研究线按模块路径挑因子，
但下游关卡只 `import sherpa.alpha.custom`，没在这里 import 的主题模块在下游注册不上。
"""

from ..base import CustomAlpha, custom_alpha
from .ml import LgbmV1, LgbmV2, MLAlpha
from .quote_activity import QuoteActivityRank
from .starter import LiquidMomentumRank, VolumeSurge, close_momentum_20

__all__ = [
    "CustomAlpha",
    "custom_alpha",
    "close_momentum_20",
    "VolumeSurge",
    "LiquidMomentumRank",
    "QuoteActivityRank",
    "MLAlpha",
    "LgbmV1",
    "LgbmV2",
]
