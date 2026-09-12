"""Alpha 基类体系：世坤101 / TradingView / 自定义三大家族共用同一套契约（设计文档第6章）。"""

from __future__ import annotations

from typing import Callable, Optional

import pandas as pd

from sherpa.data.schema import BarPanel


class Alpha:
    """所有因子/指标的公共基类。

    契约（设计文档 §6.2）：`compute(panel)` 返回跟 `panel.index`/`panel.symbols` 对齐的
    `(T, N)` DataFrame —— 一个 Alpha 只产出一条分数序列，不支持多输出。像布林带这种天生
    有好几条线的指标，拆成多个单输出子类分别注册（比如 BollingerUpper/Mid/Lower），
    而不是让 compute() 返回 dict——这样任何 Alpha 都能自由地互相组合、被 AlphaEngine
    统一拼进同一张特征矩阵，不需要为"这个因子是不是多输出"写特殊分支。
    """

    name: str = ""
    family: str = "custom"
    min_lookback: int = 1

    def __init__(self, **params):
        self.params = params
        if not self.name:
            self.name = type(self).__name__

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        raise NotImplementedError

    def latest(self, panel: BarPanel) -> pd.Series:
        """便捷方法：只取 compute() 结果的最后一行——实时/事件驱动场景只关心当前截面。"""
        result = self.compute(panel)
        if len(result) == 0:
            return pd.Series(dtype="float64", index=panel.symbols)
        return result.iloc[-1]

    @property
    def qualified_name(self) -> str:
        """带家族前缀的唯一标识，如 "worldquant.alpha006"，是 AlphaEngine 输出列名。"""
        return f"{self.family}.{self.name}"

    def __repr__(self) -> str:
        params = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"{type(self).__name__}({params})"


class AlphaRegistry:
    """按 qualified_name 索引的全局 Alpha 类登记表，方便"给我所有世坤101因子"这类枚举需求。"""

    def __init__(self):
        self._classes: dict[str, type[Alpha]] = {}

    def register(self, cls: type[Alpha]) -> type[Alpha]:
        key = f"{cls.family}.{cls.name or cls.__name__}"
        existing = self._classes.get(key)
        if existing is not None and existing is not cls:
            raise ValueError(f"duplicate alpha registration: {key!r} ({existing!r} vs {cls!r})")
        self._classes[key] = cls
        return cls

    def get(self, qualified_name: str) -> type[Alpha]:
        return self._classes[qualified_name]

    def all(self, family: Optional[str] = None) -> dict[str, type[Alpha]]:
        if family is None:
            return dict(self._classes)
        return {k: v for k, v in self._classes.items() if v.family == family}


registry = AlphaRegistry()


def register_alpha(cls: Optional[type[Alpha]] = None, *, name: Optional[str] = None):
    """类装饰器：把一个 Alpha 子类登记进全局 registry（显式注册，不用 __init_subclass__ 暗中生效）。"""

    def wrap(c: type[Alpha]) -> type[Alpha]:
        if name:
            c.name = name
        return registry.register(c)

    return wrap(cls) if cls is not None else wrap


class WorldQuantAlpha(Alpha):
    """世坤101风格因子的家族基类。子类按经济含义放进 sherpa.alpha.worldquant 下对应的分类模块。"""

    family = "worldquant"


class TradingViewIndicator(Alpha):
    """TradingView/TA-Lib 社区经典指标复刻的家族基类。"""

    family = "tradingview"


class CustomAlpha(Alpha):
    """用户自定义因子的家族基类，策略作者自己的仓库/脚本里继承它写因子。"""

    family = "custom"


def custom_alpha(name: str, *, min_lookback: int = 1):
    """函数式定义一个 custom 家族因子，适合快速试验，不用写完整的类。

    用法::

        @custom_alpha("close_momentum_20", min_lookback=21)
        def close_momentum_20(panel: BarPanel) -> pd.DataFrame:
            return panel.close.pct_change(20)

    需要参数化/持有状态的因子请直接继承 CustomAlpha 写类，装饰器只覆盖"一个纯函数就是一个因子"的场景。
    """

    def decorator(fn: Callable[[BarPanel], pd.DataFrame]) -> type[CustomAlpha]:
        def compute(self, panel: BarPanel) -> pd.DataFrame:  # noqa: ANN001
            return fn(panel)

        cls = type(
            fn.__name__,
            (CustomAlpha,),
            {"name": name, "min_lookback": min_lookback, "compute": compute, "__doc__": fn.__doc__},
        )
        return register_alpha(cls)

    return decorator
