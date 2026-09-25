"""tradability_calibration 研究项目共用的取数入口：接真实 ClickHouse，不是合成数据。

跟 `research/alpha_research/worldquant_101/data.py` 是同一套连接方式，特意原样复制一份、不共用——
`connect_ch_reader()` 是纯客户端代码（读环境变量、建连接），不含任何项目专属常量，让每个
研究项目自己维护一份更简单。

连接信息一律从环境变量读，约定跟 `scripts/smoke_test_data_layer.py` 一致：
    CH_HOST(必填) / CH_PORT(默认8123) / CH_USER(默认default) / CH_PASSWORD / CH_DATABASE(默认market)

默认区间/周期统一读 `research/research_window.json` 的研究段：这里校准出来的掩码门槛要给
阶段一、关卡1 所有体检复用，用同一段历史校准最一致，也顺带不碰 holdout 段。想临时换区间，
调用 `load_universe_panel()` 时显式传参覆盖。
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

# 时间窗统一从 `research/research_window.json` 读——阶段一、关卡1、关卡2 必须看同一段历史，
# 否则"阶段一在 A 区间选出的因子，关卡1 在 B 区间检验冗余"，两边结论对不上。说明见
# `research/README.md`「统一时间窗与样本外 holdout」。`END_TIME` 是研究段截止（= holdout
# 起点），默认取数永远不碰 holdout 段；临时换区间就调用 `load_universe_panel()` 时显式传参。
_WINDOW = json.loads((Path(__file__).resolve().parents[1] / "research_window.json").read_text(encoding="utf-8"))
INTERVAL: str = _WINDOW["interval"]
START_TIME: str = _WINDOW["research_start"]
END_TIME: str = _WINDOW["research_end"]


def _env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"missing required env var {name}")
    return value


def connect_ch_reader() -> CHReader:
    """真实 ClickHouse 连接，参数来源见模块 docstring。"""
    host = _env("CH_HOST", required=True)
    port = int(_env("CH_PORT", "8123"))
    user = _env("CH_USER", "default")
    password = _env("CH_PASSWORD", "")
    database = _env("CH_DATABASE", "market")
    client = clickhouse_connect.get_client(
        host=host, port=port, username=user, password=password, database=database
    )
    return CHReader(client, database=database)


def load_universe_panel(
    ch_reader: CHReader | None = None,
    *,
    interval: str = INTERVAL,
    start_time: str = START_TIME,
    end_time: str = END_TIME,
    include_open_interest: bool = True,
) -> BarPanel:
    """拉取指定区间/周期的全市场 K 线，拼成研究用的 `BarPanel`。

    universe 用 `Universe.as_of(end_time)`（设计文档 §5.3 的 point-in-time 口径）——避免
    把区间内还没上线/已经退市的 symbol 也当成"从头到尾都在"，防止幸存者偏差。

    `include_open_interest` 默认打开，行为跟 `alpha_research/worldquant_101/data.py`
    里同名参数一致（见那边的注释）；interval="1m" 时无效。
    """
    ch_reader = ch_reader or connect_ch_reader()
    universe = Universe.from_clickhouse(ch_reader)
    symbols = universe.as_of(pd.Timestamp(end_time, tz="UTC"))
    if not symbols:
        raise RuntimeError(f"universe.as_of({end_time!r}) 返回空列表，检查 ClickHouse 里是否真的有数据")

    long_df = ch_reader.fetch_history(symbols, interval, start_time=start_time, end_time=end_time)
    oi_df = None
    if include_open_interest and interval != "1m":
        oi_df = ch_reader.fetch_oi_history(symbols, interval, start_time=start_time, end_time=end_time)
    return ch_long_to_panel(long_df, interval=interval, symbols=symbols, oi_df=oi_df)
