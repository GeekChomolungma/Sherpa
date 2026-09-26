"""关卡2（factor_synthesis）专用的取数入口：接真实 ClickHouse，不是合成数据。

从 `research/factor_orthogonalization/data.py` 拷贝后独立维护，刻意不 import 其它 research 子项目的
`data.py`——子项目之间不共享代码、不共享中间结果，改任何一边都不会波及另一边。唯一共享的是研究
配置 `research/research_config.json`（时间窗 + IC 标签口径），必须跟阶段一、关卡1 用同一种标签，
否则候选因子是在 A 口径下选出来的、合成效果却在 B 口径下评估，结论对不上。

跟阶段一 / 关卡1 的 `data.py` 唯一的区别是**取数区间**：它们只取选择段（截止 `validation_start`），
这里取**整个研究段**（截止 `research_end`）——关卡2 要在选择段上估计方向、在验证段上比较各合成方案，
两段都要用到。

连接信息一律从环境变量读，不写进代码/仓库，跟仓库里其它 research 脚本同一套约定：

    CH_HOST(必填) / CH_PORT(默认8123) / CH_USER(默认default) / CH_PASSWORD / CH_DATABASE(默认market)
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
from sherpa.metrics.factor import forward_returns

# 研究配置统一从 `research/research_config.json` 读（说明见 `research/README.md`「统一研究配置」）。
# `window` 一节把历史切成三段（说明见 `research/README.md`「统一研究配置」）：
#   选择段 research_start ~ validation_start：阶段一体检、关卡1 去冗余只在这一段上做；关卡2 在这一段上
#                                            估计各因子的方向（IC 符号）；
#   验证段 validation_start ~ research_end：关卡2 比较各合成方案，对"选因子"来说是没见过的数据；
#   holdout research_end ~ holdout_end：最终方案只跑一次，本模块默认不取。
# 本模块取整个研究段 research_start ~ research_end，再用 `VALIDATION_START` 切成两段。
_CONFIG = json.loads((Path(__file__).resolve().parents[1] / "research_config.json").read_text(encoding="utf-8"))
INTERVAL: str = _CONFIG["window"]["interval"]
START_TIME: str = _CONFIG["window"]["research_start"]
END_TIME: str = _CONFIG["window"]["research_end"]  # 整个研究段（选择段 + 验证段），不含 holdout
VALIDATION_START: str = _CONFIG["window"]["validation_start"]

# `label` 一节：IC 检验用的"未来收益"标签口径（持有几根 bar、信号出来后延迟几根 bar 才成交）。
# 所有算 IC 的脚本（阶段一体检、关卡1 挑代表因子、关卡2 评估合成分数）必须用同一个口径，否则阶段一按"延迟 1 根"
# 选出的因子，关卡1 却按"不延迟"比强弱，前后对不上。一律通过下面的 `label_forward_returns()` 取标签。
HORIZON_BARS: int = int(_CONFIG["label"]["horizon_bars"])
EXECUTION_DELAY_BARS: int = int(_CONFIG["label"]["execution_delay_bars"])


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

    universe 用 `Universe.as_of(end_time)`（point-in-time 口径），避免把区间内还没上线/
    已经退市的 symbol 也当成"从头到尾都在"，防止幸存者偏差。

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


def label_forward_returns(panel: BarPanel) -> pd.DataFrame:
    """按 `research_config.json` 的 `label` 配置构造 IC 标签：t 行 = 从 `close[t + delay]` 持有到
    `close[t + delay + horizon]` 的收益（`sherpa.metrics.factor.forward_returns`）。

    默认 `horizon_bars=1, execution_delay_bars=0` 等价于历史写法 `panel.close.pct_change().shift(-1)`；
    `execution_delay_bars=1` 等价于 `shift(-2)`，模拟"信号出来后晚一根 bar 才成交"。
    """
    return forward_returns(panel.close, horizon=HORIZON_BARS, delay=EXECUTION_DELAY_BARS)
