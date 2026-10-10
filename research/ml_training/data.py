"""ML alpha 滚动训练专用的取数入口：接真实 ClickHouse。

按 research 子项目的约定从 `research/friction_test/data.py` 拷贝后独立维护，不 import 其它子项目。唯一共享的是
`research/research_config.json`：时间窗、标签口径、大盘锚点必须跟阶段一和各关卡一致——训练用的标签就是研究
流水线评估 IC 用的那个标签。

取数区间：从 `research_start` 开始（跟阶段一、关卡3 同一个起点，特征的 warm-up 行为一致），默认到 `research_end`；
要让模型覆盖 holdout 时传 `end_time=HOLDOUT_END`（研究结论定下来之前不要这么做）。

连接信息从环境变量读：CH_HOST(必填) / CH_PORT(默认8123) / CH_USER(默认default) / CH_PASSWORD / CH_DATABASE(默认market)
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import clickhouse_connect
import pandas as pd

from sherpa.data.ch_reader import CHReader
from sherpa.data.normalizer import ch_long_to_panel
from sherpa.data.schema import BarPanel
from sherpa.data.universe import Universe

_CONFIG = json.loads((Path(__file__).resolve().parents[1] / "research_config.json").read_text(encoding="utf-8"))
INTERVAL: str = _CONFIG["window"]["interval"]
START_TIME: str = _CONFIG["window"]["research_start"]
VALIDATION_START: str = _CONFIG["window"]["validation_start"]
END_TIME: str = _CONFIG["window"]["research_end"]
HOLDOUT_END: str = _CONFIG["window"]["holdout_end"]
BENCHMARK_SYMBOL: str = _CONFIG["market"]["benchmark_symbol"]
HORIZON_BARS: int = int(_CONFIG["label"]["horizon_bars"])
EXECUTION_DELAY_BARS: int = int(_CONFIG["label"]["execution_delay_bars"])


def _env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"missing required env var {name}")
    return value


def connect_ch_reader() -> CHReader:
    client = clickhouse_connect.get_client(
        host=_env("CH_HOST", required=True),
        port=int(_env("CH_PORT", "8123")),
        username=_env("CH_USER", "default"),
        password=_env("CH_PASSWORD", ""),
        database=_env("CH_DATABASE", "market"),
    )
    return CHReader(client, database=_env("CH_DATABASE", "market"))


def load_universe_panel(
    ch_reader: CHReader | None = None,
    *,
    interval: str = INTERVAL,
    start_time: str = START_TIME,
    end_time: str = END_TIME,
    include_open_interest: bool = True,
    include_long_short_ratio: bool = True,
) -> BarPanel:
    """同各关卡：universe 用 `Universe.as_of(end_time)`，还没上线的币在上线前整列是 NaN，特征构建会跳过。"""
    ch_reader = ch_reader or connect_ch_reader()
    universe = Universe.from_clickhouse(ch_reader)
    symbols = universe.as_of(pd.Timestamp(end_time, tz="UTC"))
    if not symbols:
        raise RuntimeError(f"universe.as_of({end_time!r}) 返回空列表，检查 ClickHouse 里是否真的有数据")

    long_df = ch_reader.fetch_history(symbols, interval, start_time=start_time, end_time=end_time)
    oi_df = None
    if include_open_interest and interval != "1m":
        oi_df = ch_reader.fetch_oi_history(symbols, interval, start_time=start_time, end_time=end_time)
    ls_df = None
    if include_long_short_ratio and interval != "1m":
        ls_df = ch_reader.fetch_ls_ratio_history(symbols, interval, start_time=start_time, end_time=end_time)
    return ch_long_to_panel(long_df, interval=interval, symbols=symbols, oi_df=oi_df, ls_df=ls_df)
