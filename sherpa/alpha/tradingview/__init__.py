"""TradingView / TA-Lib 社区经典指标复刻（设计文档 §6.3）。

已实现：RSI、ATR。后续按需添加（BOLL/SuperTrend/KDJ/CMF/...），每个指标一个文件，
继承 TradingViewIndicator，用 @register_alpha 注册；多输出的指标（比如布林带的上中下轨）
拆成多个单输出类，参考 sherpa.data 的设计文档 §6.2。
"""

from .atr import ATR
from .rsi import RSI

__all__ = ["RSI", "ATR"]
