"""Alpha / Feature 引擎（设计文档第6章）：BarPanel -> 特征矩阵。

只导入框架本身（ops/base/engine），不预加载 worldquant/tradingview/custom 三个家族——
按需 `import sherpa.alpha.worldquant` 之类的子包，才会触发里面因子的 @register_alpha
注册，避免用不到的因子也被强制加载。
"""

from . import ops
from .base import (
    Alpha,
    AlphaRegistry,
    CustomAlpha,
    TradingViewIndicator,
    WorldQuantAlpha,
    custom_alpha,
    register_alpha,
    registry,
)
from .engine import AlphaEngine

__all__ = [
    "ops",
    "Alpha",
    "AlphaRegistry",
    "registry",
    "register_alpha",
    "WorldQuantAlpha",
    "TradingViewIndicator",
    "CustomAlpha",
    "custom_alpha",
    "AlphaEngine",
]
