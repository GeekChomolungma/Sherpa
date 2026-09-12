"""AlphaEngine：把一组 Alpha 对同一个 BarPanel 的计算结果拼成特征矩阵（设计文档 §6.4）。"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from sherpa.data.schema import BarPanel

from .base import Alpha


class AlphaEngine:
    """Pipeline 层直接用的入口：`features = alpha_engine.compute(event.panel)`。"""

    def __init__(self, alphas: Sequence[Alpha]):
        self._alphas = list(alphas)
        names = [a.qualified_name for a in self._alphas]
        if len(names) != len(set(names)):
            raise ValueError(f"AlphaEngine 里有重复的 qualified_name: {names}")

    @property
    def alphas(self) -> list[Alpha]:
        return list(self._alphas)

    @property
    def required_lookback(self) -> int:
        """本引擎里所有 alpha 需要的最小回看根数——配置 panel_source 的 lookback_bars 时参考这个
        （设计文档 §6.2），本身不会去改 panel_source 的配置，只是暴露出来给 Pipeline/Runner 层用。
        """
        return max((a.min_lookback for a in self._alphas), default=1)

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        """(symbol x alpha名) 截面特征矩阵：index=symbol, columns=各 alpha 的 qualified_name。"""
        return pd.DataFrame({a.qualified_name: a.latest(panel) for a in self._alphas})

    def compute_history(self, panel: BarPanel) -> dict[str, pd.DataFrame]:
        """向量化回测/因子研究用：每个 alpha 的完整 (T,N) 历史，key=qualified_name。"""
        return {a.qualified_name: a.compute(panel) for a in self._alphas}
