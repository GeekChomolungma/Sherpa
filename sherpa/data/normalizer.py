"""把 ClickHouse 长表 / Redis 原始结构映射成 BarPanel（设计文档 5.2.1、5.5）。

这是唯一允许知道"上游原始格式长什么样"的模块——CHReader/RedisReader 只管 I/O，
指标层只认 BarPanel，中间的格式转换全部收敛在这里。
"""

from __future__ import annotations

from typing import Mapping, Sequence

import pandas as pd

from .schema import PANEL_FIELDS, BarPanel, build_coverage, empty_panel

# ClickHouse 长表期望列（顺序对应 PANEL_FIELDS，前面多一个 symbol/start_time）。
CH_LONG_FORM_COLUMNS: tuple[str, ...] = ("symbol", "start_time", *PANEL_FIELDS)

# Redis kline:{SYM}:1m 紧凑数组：[0]=start_time, [1..9] 对应 PANEL_FIELDS（设计文档 §3）。
_REDIS_ARRAY_LEN = 1 + len(PANEL_FIELDS)


def redis_rows_to_frame(rows: Sequence[Sequence]) -> pd.DataFrame:
    """把一个 symbol 的 Redis 紧凑数组列表（任意顺序）转成按时间升序的单 symbol DataFrame。"""
    if not rows:
        return pd.DataFrame(columns=PANEL_FIELDS, dtype="float64")

    index = []
    columns: dict[str, list[float]] = {name: [] for name in PANEL_FIELDS}
    for row in rows:
        if len(row) != _REDIS_ARRAY_LEN:
            raise ValueError(
                f"Redis kline 数组长度应为 {_REDIS_ARRAY_LEN}（start_time + {len(PANEL_FIELDS)} 个字段），"
                f"实际为 {len(row)}：{row!r}"
            )
        index.append(pd.Timestamp(int(row[0]), unit="ms", tz="UTC"))
        for offset, name in enumerate(PANEL_FIELDS, start=1):
            columns[name].append(float(row[offset]))

    frame = pd.DataFrame(columns, index=pd.DatetimeIndex(index, name="start_time"))
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame.sort_index().astype("float64")


def frames_to_panel(
    per_symbol_frames: Mapping[str, pd.DataFrame],
    *,
    interval: str,
    symbols: Sequence[str],
) -> BarPanel:
    """把 {symbol: 单symbol宽表(index=start_time, columns=PANEL_FIELDS)} 拼成一个 BarPanel。

    对齐规则（设计文档 5.3）：行 index 取所有 symbol 的并集，缺失格一律 NaN，不做 ffill。
    """
    symbols_final = tuple(sorted(set(symbols) | set(per_symbol_frames.keys())))
    non_empty = {sym: f for sym, f in per_symbol_frames.items() if not f.empty}

    if not non_empty:
        return empty_panel(interval, symbols_final)

    union_index = pd.DatetimeIndex(
        sorted(set().union(*(f.index for f in non_empty.values()))),
        tz="UTC",
        name="start_time",
    )

    fields: dict[str, pd.DataFrame] = {}
    for field_name in PANEL_FIELDS:
        wide = pd.DataFrame(index=union_index, columns=symbols_final, dtype="float64")
        for sym, frame in non_empty.items():
            wide[sym] = frame[field_name].reindex(union_index)
        fields[field_name] = wide

    coverage = build_coverage(fields["close"], universe_size=len(symbols_final))
    return BarPanel(interval=interval, symbols=symbols_final, coverage=coverage, **fields)


def ch_long_to_panel(df: pd.DataFrame, *, interval: str, symbols: Sequence[str]) -> BarPanel:
    """ClickHouse 长表（一次 fetch_history 的结果）-> BarPanel。

    要求 df 至少包含 CH_LONG_FORM_COLUMNS 里除 start_time 类型转换外的所有列；
    不要求带 FINAL/去重——但如果 df 里有重复的 (symbol, start_time)，pivot 会直接报错，
    这本身就是"忘记 FINAL"的一个天然探测（见设计文档 §3 上游硬性要求）。
    """
    symbols_final = tuple(sorted(set(symbols) | (set(df["symbol"].unique()) if not df.empty else set())))

    if df.empty:
        return empty_panel(interval, symbols_final)

    df = df.copy()
    df["start_time"] = pd.to_datetime(df["start_time"], utc=True)

    fields: dict[str, pd.DataFrame] = {}
    index: pd.DatetimeIndex | None = None
    for field_name in PANEL_FIELDS:
        try:
            pivoted = df.pivot(index="start_time", columns="symbol", values=field_name)
        except ValueError as exc:
            raise ValueError(
                "ClickHouse 结果里存在重复的 (symbol, start_time) —— 查询是否忘记加 FINAL？"
            ) from exc
        pivoted = pivoted.reindex(columns=symbols_final).sort_index().astype("float64")
        fields[field_name] = pivoted
        index = pivoted.index

    coverage = build_coverage(fields["close"], universe_size=len(symbols_final))
    return BarPanel(interval=interval, symbols=symbols_final, coverage=coverage, **fields)


def redis_window_to_panel(
    raw: Mapping[str, Sequence[Sequence]],
    *,
    interval: str,
    symbols: Sequence[str],
) -> BarPanel:
    """Redis kline:{SYM}:1m 批量拉取结果（RedisReader.get_closed_window 的返回值）-> BarPanel。"""
    if interval != "1m":
        raise ValueError("redis_window_to_panel 只适用于 1m（Redis 滚动窗口只有 1m，见设计文档 §3）")
    per_symbol_frames = {sym: redis_rows_to_frame(rows) for sym, rows in raw.items()}
    return frames_to_panel(per_symbol_frames, interval=interval, symbols=symbols)
