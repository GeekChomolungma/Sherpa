"""手动烟雾测试：接一次真实 ClickHouse/Redis，跑一遍数据接入层的主要路径。

不是单元测试（不在 pytest 里跑），单纯用来验证 sherpa.data 对着真实环境能不能跑通。
连接信息一律从环境变量读，不写进代码/仓库：

    CH_HOST / CH_PORT(默认8123) / CH_USER(默认default) / CH_PASSWORD / CH_DATABASE(默认market)
    REDIS_HOST / REDIS_PORT(默认6379) / REDIS_DB(默认0) / REDIS_PASSWORD

用法：
    CH_HOST=... CH_PASSWORD=... REDIS_HOST=... REDIS_PASSWORD=... python scripts/smoke_test_data_layer.py
"""

from __future__ import annotations

import os
import sys

import clickhouse_connect
import redis

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sherpa.data.ch_reader import CHReader
from sherpa.data.normalizer import ch_long_to_panel, redis_window_to_panel
from sherpa.data.redis_reader import RedisReader
from sherpa.data.universe import Universe
from sherpa.data.window_cache import WindowCache


def _env(name: str, default: str | None = None, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise SystemExit(f"missing required env var {name}")
    return value


def main() -> None:
    ch_host = _env("CH_HOST", required=True)
    ch_port = int(_env("CH_PORT", "8123"))
    ch_user = _env("CH_USER", "default")
    ch_password = _env("CH_PASSWORD", "")
    ch_database = _env("CH_DATABASE", "market")

    redis_host = _env("REDIS_HOST", required=True)
    redis_port = int(_env("REDIS_PORT", "6379"))
    redis_db = int(_env("REDIS_DB", "0"))
    redis_password = _env("REDIS_PASSWORD", "") or None

    print(f"== connecting ClickHouse {ch_host}:{ch_port}/{ch_database} ==")
    ch_client = clickhouse_connect.get_client(
        host=ch_host, port=ch_port, username=ch_user, password=ch_password, database=ch_database
    )
    ch_reader = CHReader(ch_client, database=ch_database)

    print(f"== connecting Redis {redis_host}:{redis_port}/{redis_db} ==")
    redis_client = redis.Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        password=redis_password,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
    )
    redis_client.ping()
    redis_reader = RedisReader(redis_client)

    print("\n-- CHReader.get_all_symbols() --")
    all_symbols = ch_reader.get_all_symbols()
    print(f"{len(all_symbols)} symbols, sample: {all_symbols[:5]}")
    if not all_symbols:
        raise SystemExit("no symbols found in ClickHouse — nothing to smoke test against")

    sample = sorted(all_symbols[:5])

    print("\n-- CHReader.fetch_history(lookback_bars=5) --")
    long_df = ch_reader.fetch_history(sample, "1h", lookback_bars=5)
    print(f"{len(long_df)} rows, columns={list(long_df.columns)}")
    panel = ch_long_to_panel(long_df, interval="1h", symbols=sample)
    print(f"BarPanel: interval={panel.interval} shape={panel.close.shape} coverage_tail={panel.coverage.tail(1).values}")

    print("\n-- Universe point-in-time (get_listing_times, may take a bit - full table GROUP BY) --")
    universe = Universe.from_clickhouse(ch_reader)
    listed_recent = universe.as_of(panel.index[-1] if len(panel.index) else "2020-01-01")
    print(f"{len(listed_recent)} symbols listed as of the latest bar we pulled")

    print("\n-- RedisReader.get_closed_window --")
    raw_window = redis_reader.get_closed_window(sample, count=200)
    for sym, rows in raw_window.items():
        print(f"  {sym}: {len(rows)} closed bars in the 1m window")
    redis_panel = redis_window_to_panel(raw_window, interval="1m", symbols=sample)
    print(f"BarPanel from redis: shape={redis_panel.close.shape}")

    print("\n-- RedisReader.get_livebar --")
    for sym in sample[:3]:
        livebar = redis_reader.get_livebar(sym)
        print(f"  {sym}: {livebar}")

    print("\n-- WindowCache seed --")
    cache = WindowCache(redis_reader, universe=sample, window_size=200)
    cache.seed()
    seeded_panel = cache._build_panel()
    print(f"WindowCache seeded panel shape={seeded_panel.close.shape}")

    print("\n-- RedisReader.read_kline_ready (replay last few, non-blocking) --")
    events = redis_reader.read_kline_ready(last_id="0", block_ms=1000, count=5)
    for e in events:
        print(f"  {e}")
    if not events:
        print("  (no events replayed — stream may be empty or this consumer never read from '0' before)")

    print("\nOK - data feed layer smoke test finished without errors.")


if __name__ == "__main__":
    main()
