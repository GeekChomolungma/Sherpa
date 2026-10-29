"""交易经验 alpha（tradecraft）：把币圈手动交易的经验规则写成截面打分，研究线在 `research/alpha_research/tradecraft/`。

| 文件 | 内容 |
| --- | --- |
| `base.py` | `TradecraftAlpha` 基类（打分约定、流动性范围、参数写法）和默认流动性范围 `TRADECRAFT_LIQUIDITY` |
| `indicators.py` | 共用指标：`BarPanel` → `(T, N)` 原始值（涨跌幅、区间位置、放量倍数、主动买占比、OI 变化、多空比 z 分数……） |
| `liquidity_surge.py` | 放量蓄势（`LiquiditySurgeBase` 参数化规则 + 实例 `TcSurgeCalmV1` / `V2` / `GatedV1` / `V2H2` / `V2H3`） |
| `wyckoff.py` | 威科夫区间假突破 + 量价（`WyckoffBase` + 实例 `TcWyckoffVideoV1` / `TcWyckoffAbsorbV1` / `TcWyckoffLsV1`），素材在 `materials/` |
| `demo.py` | `TcDemoReversal`：打通管道用的示例，不是交易经验 |

**加一个新 alpha**：一个主题一个文件（比如 `breakout.py`），照 `demo.py` 写 `TradecraftAlpha` 子类，然后在下面 import——
import 才会触发 `@register_alpha`，研究线才找得到它。详细步骤见 `README.md`。
"""

from .base import TRADECRAFT_LIQUIDITY, TradecraftAlpha
from .demo import TcDemoReversal
from .liquidity_surge import (
    LiquiditySurgeBase, TcSurgeCalmGatedV1, TcSurgeCalmV1, TcSurgeCalmV2, TcSurgeCalmV2H2, TcSurgeCalmV2H3,
)
from .wyckoff import TcWyckoffAbsorbV1, TcWyckoffLsV1, TcWyckoffVideoV1, WyckoffBase

__all__ = [
    "TRADECRAFT_LIQUIDITY", "TradecraftAlpha", "TcDemoReversal",
    "LiquiditySurgeBase", "TcSurgeCalmV1", "TcSurgeCalmV2", "TcSurgeCalmGatedV1", "TcSurgeCalmV2H2", "TcSurgeCalmV2H3",
    "WyckoffBase", "TcWyckoffVideoV1", "TcWyckoffAbsorbV1", "TcWyckoffLsV1",
]
