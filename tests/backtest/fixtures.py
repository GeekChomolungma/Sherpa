"""测试用：从一份收盘价 DataFrame 造一个结构合法的 BarPanel（其余字段跟 close 相同，
vectorized/event_driven 只用得到 close 和 interval，不需要真实 OHLCV 关系）。"""

from __future__ import annotations

import pandas as pd

from sherpa.data.schema import PANEL_FIELDS, BarPanel, build_coverage


def panel_from_close(close: pd.DataFrame, interval: str = "1m") -> BarPanel:
    symbols = tuple(close.columns)
    fields = {name: close.copy() for name in PANEL_FIELDS if name != "close"}
    coverage = build_coverage(close, universe_size=len(symbols))
    return BarPanel(interval=interval, symbols=symbols, coverage=coverage, close=close, **fields)
