"""世坤101研究项目共用的取数入口：接真实 ClickHouse，不是合成数据（对比 examples/ 下的
教学示例，那些用 `FakeClickHouseClient` 站台）。

连接信息一律从环境变量读，不写进代码/仓库——跟 `scripts/smoke_test_data_layer.py` 同一套
约定：

    CH_HOST(必填) / CH_PORT(默认8123) / CH_USER(默认default) / CH_PASSWORD / CH_DATABASE(默认market)

默认取 2026-01-01 ~ 2026-09-01 的 4 小时 K 线全市场数据（`INTERVAL`/`START_TIME`/`END_TIME`
三个常量），这是当前这一批世坤101研究要跑的具体区间；以后如果要换区间/周期，改这三个常量
或者调用 `load_universe_panel()` 时显式传参覆盖，不用碰其余代码。
"""

from __future__ import annotations

import os

import clickhouse_connect
import pandas as pd

from sherpa.data.ch_reader import CHReader
from sherpa.data.normalizer import ch_long_to_panel
from sherpa.data.schema import BarPanel
from sherpa.data.universe import Universe

INTERVAL = "1d"
START_TIME = "2020-01-01"
END_TIME = "2026-09-15"


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
) -> BarPanel:
    """拉取指定区间/周期的全市场 K 线，拼成研究用的 `BarPanel`。

    universe 用 `Universe.as_of(end_time)`（设计文档 §5.3 的 point-in-time 口径）——避免
    把区间内还没上线/已经退市的 symbol 也当成"从头到尾都在"，防止幸存者偏差。
    """
    ch_reader = ch_reader or connect_ch_reader()
    universe = Universe.from_clickhouse(ch_reader)
    symbols = universe.as_of(pd.Timestamp(end_time, tz="UTC"))
    if not symbols:
        raise RuntimeError(f"universe.as_of({end_time!r}) 返回空列表，检查 ClickHouse 里是否真的有数据")

    long_df = ch_reader.fetch_history(symbols, interval, start_time=start_time, end_time=end_time)
    return ch_long_to_panel(long_df, interval=interval, symbols=symbols)
