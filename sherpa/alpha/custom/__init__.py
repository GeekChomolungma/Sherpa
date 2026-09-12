"""自定义因子家族（设计文档 §6.3）：继承 CustomAlpha 写类，或用 @custom_alpha 装饰函数。"""

from ..base import CustomAlpha, custom_alpha
from .examples import VolumeSurge, close_momentum_20

__all__ = ["CustomAlpha", "custom_alpha", "close_momentum_20", "VolumeSurge"]
