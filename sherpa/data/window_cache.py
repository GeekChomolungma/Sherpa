"""1m 滚动窗口的有状态缓存（设计文档 5.5）——数据接入层里唯一有状态的组件。

粗周期（5m/15m/1h/4h/1d）不使用本类：按 v0.2 决策，每次 kline_ready 触发时直接现查
ClickHouse 的完整 lookback，逻辑在 sherpa.data.panel_source.LivePanelSource 里。
"""

from __future__ import annotations

from typing import Sequence

import pandas as pd

from .normalizer import frames_to_panel, redis_rows_to_frame
from .redis_reader import KlineReadyEvent, RedisReader
from .schema import BarPanel, MarketEvent


class WindowCache:
    INTERVAL = "1m"

    def __init__(self, redis_reader: RedisReader, *, universe: Sequence[str], window_size: int = 200):
        self._redis = redis_reader
        self._universe = sorted(universe)
        self._window_size = window_size
        self._frames: dict[str, pd.DataFrame] = {}
        self._seeded = False

    def seed(self) -> None:
        """启动时用 kline:{SYM}:1m 的最近 200 根做初始窗口（设计文档 5.5）。"""
        raw = self._redis.get_closed_window(self._universe, count=self._window_size)
        self._frames = {sym: redis_rows_to_frame(rows) for sym, rows in raw.items()}
        self._seeded = True

    def on_kline_ready(self, event: KlineReadyEvent) -> MarketEvent:
        """收到 1m kline_ready 通知后：拉最新一根、增量 append、弹出最旧一根、产出 MarketEvent。"""
        if event.interval != self.INTERVAL:
            raise ValueError(f"WindowCache 只处理 interval={self.INTERVAL!r} 的事件，收到 {event.interval!r}")
        if not self._seeded:
            self.seed()

        latest = self._redis.get_latest_closed_bars(self._universe)
        for sym, row in latest.items():
            if row is not None:
                self._append_row(sym, row)

        panel = self._build_panel()
        return MarketEvent.build(
            interval=self.INTERVAL,
            bar_start_time=pd.Timestamp(event.timestamp_ms, unit="ms", tz="UTC"),
            symbols_count=event.symbols_count,
            universe_size=len(self._universe),
            panel=panel,
        )

    def _append_row(self, symbol: str, row: list) -> None:
        new_frame = redis_rows_to_frame([row])
        existing = self._frames.get(symbol)
        if existing is not None and not existing.empty and existing.index[-1] >= new_frame.index[-1]:
            return  # 这根 bar 已经 append 过了（幂等，防止重复处理同一次通知）
        frame = new_frame if existing is None or existing.empty else pd.concat([existing, new_frame])
        if len(frame) > self._window_size:
            frame = frame.iloc[-self._window_size :]
        self._frames[symbol] = frame

    def _build_panel(self) -> BarPanel:
        return frames_to_panel(self._frames, interval=self.INTERVAL, symbols=self._universe)
