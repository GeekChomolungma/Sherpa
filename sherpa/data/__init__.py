"""数据接入层 + 数据契约（设计文档 docs/SHERPA_DESIGN.md 第 5 章）。"""

from .ch_reader import CHReader
from .normalizer import ch_long_to_panel, frames_to_panel, redis_rows_to_frame, redis_window_to_panel
from .panel_source import HistoricalPanelSource, IPanelSource, LivePanelSource
from .redis_reader import KlineReadyEvent, RedisReader
from .schema import (
    PANEL_FIELDS,
    SCHEMA_VERSION,
    VALID_INTERVALS,
    BarPanel,
    MarketEvent,
    build_coverage,
    empty_panel,
    interval_to_timedelta,
)
from .universe import Universe
from .window_cache import WindowCache

__all__ = [
    "CHReader",
    "RedisReader",
    "KlineReadyEvent",
    "Universe",
    "WindowCache",
    "BarPanel",
    "MarketEvent",
    "PANEL_FIELDS",
    "SCHEMA_VERSION",
    "VALID_INTERVALS",
    "build_coverage",
    "empty_panel",
    "interval_to_timedelta",
    "ch_long_to_panel",
    "redis_window_to_panel",
    "redis_rows_to_frame",
    "frames_to_panel",
    "IPanelSource",
    "HistoricalPanelSource",
    "LivePanelSource",
]
