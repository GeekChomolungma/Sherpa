"""Universe 管理：symbol 全集来源 + point-in-time 过滤（设计文档 5.3）。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from .ch_reader import CHReader

_MAX_TS = pd.Timestamp.max.tz_localize("UTC")


class Universe:
    """symbol 全集：可以是静态列表（universe.txt），也可以来自 CHReader.get_all_symbols()。"""

    def __init__(self, symbols: Optional[Sequence[str]] = None, *, ch_reader: Optional[CHReader] = None):
        if symbols is None and ch_reader is None:
            raise ValueError("Universe 需要静态 symbol 列表或 CHReader 至少给一个")
        self._static_symbols = sorted(set(symbols)) if symbols is not None else None
        self._ch_reader = ch_reader
        self._listing_times: Optional[dict[str, pd.Timestamp]] = None

    @classmethod
    def from_file(cls, path: str, *, ch_reader: Optional[CHReader] = None) -> "Universe":
        text = Path(path).read_text(encoding="utf-8")
        symbols = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        return cls(symbols, ch_reader=ch_reader)

    @classmethod
    def from_clickhouse(cls, ch_reader: CHReader) -> "Universe":
        return cls(None, ch_reader=ch_reader)

    def all_symbols(self) -> list[str]:
        if self._static_symbols is not None:
            return list(self._static_symbols)
        return self._ch_reader.get_all_symbols()

    def as_of(self, t) -> list[str]:
        """point-in-time universe：只返回在时间 t 已经上线的 symbol（防止回测幸存者偏差，见设计文档 5.3）。

        依赖 CHReader.get_listing_times()（用 min(start_time) 倒推上线时间）；结果在本次
        Universe 生命周期内缓存，不重复查询整张表。没有 CHReader 时无法判断上线时间，报错提醒
        调用方——不要静默退化成"全量 symbol"，那样会悄悄引入幸存者偏差。
        """
        if self._ch_reader is None:
            raise RuntimeError(
                "point-in-time universe 需要 CHReader 来查询上线时间（当前 Universe 是纯静态列表，未注入 CHReader）"
            )
        t = pd.Timestamp(t)
        if t.tzinfo is None:
            t = t.tz_localize("UTC")
        listing_times = self._listing_times_cache()
        candidates = self.all_symbols()
        return sorted(s for s in candidates if listing_times.get(s, _MAX_TS) <= t)

    def _listing_times_cache(self) -> dict[str, pd.Timestamp]:
        if self._listing_times is None:
            self._listing_times = self._ch_reader.get_listing_times()
        return self._listing_times
