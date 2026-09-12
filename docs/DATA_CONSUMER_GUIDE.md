> **Language:** English | [简体中文](DATA_CONSUMER_GUIDE.zh-CN.md)

# ChomoSyncer-go Data Consumer Guide

**Audience**: a downstream Python (or any other language) consumer that reads market data produced by `ChomoSyncer-go`. It does **not** need to run, deploy, or understand the Go internals — it only needs to know what exists, what shape it's in, and how to read it.

This is a **reference for consuming the data**, not for how it's produced. For the producer-side mechanics (goroutine models, concurrency, internal Go structs, line-by-line code entry points), see [`DATA_FLOW_AND_STRUCTURES.md`](DATA_FLOW_AND_STRUCTURES.md) instead — this guide is the short version aimed at "I just want to read the data correctly."

---

## The Two Producers, at a Glance

Everything downstream reads from exactly two stores, written by one pipeline:

| # | Store | What's in it | Structure | Symbols covered | History depth |
| :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | **ClickHouse** (`market` database) | 1m raw archive + 5m/15m/1h/4h/1d rollups | SQL tables | All intervals, full market | Full history (years) |
| 2a | **Redis** — `livebar:{SYM}:1m` | The still-forming, unclosed current bar | Hash | 1m only | 1 bar (overwritten every update) |
| 2b | **Redis** — `kline:{SYM}:1m` | The last 200 **closed** 1m bars | List | 1m only | 200 bars (~3h20m) |
| 2c | **Redis** — `stream:market:kline_ready` | "a whole market cross-section just closed" notification | Stream | All intervals (see note below) | Last `stream_maxlen` events (default 10,000) |

**Rule of thumb for which one to read:**
- Need a live, still-updating current price/volume for `1m`? → **livebar**.
- Need a fast rolling feature window over the last ~3 hours of closed `1m` bars, market-wide, in one round trip? → **closed window**.
- Need to know the instant the whole market's bars for a period are ready (to trigger a computation)? → **kline_ready**, then pull the actual bars from Redis (`1m`) or ClickHouse (coarser).
- Need anything older than ~3 hours, or any interval other than `1m`? → **ClickHouse**, always.

---

## Connection Basics

| | Default | Where it's set |
| :--- | :--- | :--- |
| ClickHouse native (Go writer) | `9000` | `clickhouse.addrs` in `config.yaml` |
| ClickHouse HTTP (what Python clients use) | `8123` | same host, fixed offset from native |
| ClickHouse database | `market` | `clickhouse.database` |
| Redis | `6379`, db `0` | `redis.addr` / `redis.db` |

Get the real host/port/credentials for your environment from whoever deployed it (`config.yaml`) — this guide assumes you already have connectivity.

```bash
pip install redis clickhouse-connect
```

---

## 1. ClickHouse — the archive of record

### Tables

`market.fapi_kline_1m` is the only table the collector writes directly. Every coarser interval is a materialized-view rollup, recomputed from `fapi_kline_1m`, never touched by hand:

| Table | Interval |
| :--- | :--- |
| `market.fapi_kline_1m` | 1 minute |
| `market.fapi_kline_5m` | 5 minutes |
| `market.fapi_kline_15m` | 15 minutes |
| `market.fapi_kline_1h` | 1 hour |
| `market.fapi_kline_4h` | 4 hours |
| `market.fapi_kline_1d` | 1 day |

All six tables share the same column layout:

| Column | Type | Meaning |
| :--- | :--- | :--- |
| `symbol` | `LowCardinality(String)` | e.g. `"BTCUSDT"` |
| `start_time` | `DateTime64(3, 'UTC')` | Bar open time, UTC, millisecond precision. **The primary key** — join/align on this. |
| `end_time` | `DateTime64(3, 'UTC')` | Bar close time, UTC. |
| `open` / `high` / `low` / `close` | `Float64` | OHLC. |
| `volume` | `Float64` | Base-asset traded volume. |
| `quote_volume` | `Float64` | Quote-asset (USDT) traded turnover. |
| `taker_buy_volume` | `Float64` | Taker-buy base-asset volume (useful for order-flow / CVD). |
| `taker_buy_quote_volume` | `Float64` | Taker-buy quote-asset turnover. |
| `trades_count` | `UInt32` | Number of matched trades in the bar. |
| `created_at` *(1m table only)* / `rollup_version` *(rollup tables)* | `DateTime` / `DateTime64(3,'UTC')` | Internal — used by ClickHouse for dedup on merge. Ignore it unless debugging. |

> ⚠️ **Always query with `FINAL`.** The engine is `ReplacingMergeTree`, which dedupes `(symbol, start_time)` in the *background* on merge — an un-merged table can transiently have more than one physical row for the same bar. `FINAL` forces read-time dedup. Every example below uses it; don't drop it.

### Reading it

```python
import clickhouse_connect

client = clickhouse_connect.get_client(
    host="localhost", port=8123, username="default", password="", database="market"
)

# Last 7 days of 1h bars for one symbol, as a DataFrame
df = client.query_df("""
    SELECT symbol, start_time, end_time, open, high, low, close,
           volume, quote_volume, taker_buy_volume, taker_buy_quote_volume, trades_count
    FROM market.fapi_kline_1h FINAL
    WHERE symbol = 'BTCUSDT' AND start_time >= now() - INTERVAL 7 DAY
    ORDER BY start_time ASC
""")

# The whole market's cross-section at one specific closed bar
snapshot = client.query_df("""
    SELECT symbol, close, quote_volume, trades_count
    FROM market.fapi_kline_1h FINAL
    WHERE start_time = '2026-09-07 16:00:00'
    ORDER BY quote_volume DESC
""")
```

```bash
# Same thing from the CLI, if you just want to look
clickhouse-client --query "
SELECT symbol, start_time, close, volume
FROM market.fapi_kline_1m FINAL
WHERE symbol = 'BTCUSDT' ORDER BY start_time DESC LIMIT 5
FORMAT PrettyCompact"
```

---

## 2. Redis — `livebar:{SYMBOL}:1m` (unclosed, live snapshot)

The currently-forming bar for a symbol, updated many times per second while it's open. **Only exists for `1m`** — there is no `livebar:*:5m` etc.

- **Key**: `livebar:{SYMBOL}:1m`, symbol **uppercase** (e.g. `livebar:BTCUSDT:1m`)
- **Type**: Redis `Hash`
- **TTL**: `2 × interval` (120s for 1m) — if the collector stops updating a symbol, the key self-expires; a missing key is not necessarily an error, check freshness (`t`) first.

| Hash field | Meaning | Python cast |
| :--- | :--- | :--- |
| `t` | Bar open time, epoch ms (UTC) | `int(v)` |
| `o` | Open | `float(v)` |
| `h` | High so far | `float(v)` |
| `l` | Low so far | `float(v)` |
| `c` | Latest price (current close-so-far) | `float(v)` |
| `v` | Cumulative base volume so far | `float(v)` |
| `qv` | Cumulative quote (USDT) volume so far | `float(v)` |
| `tbv` | Taker-buy base volume so far | `float(v)` |
| `tbqv` | Taker-buy quote volume so far | `float(v)` |
| `n` | Trades so far | `int(v)` |
| `x` | `"1"` if this bar just closed, `"0"` while still forming | `v == "1"` |

> ⚠️ **Every value comes back as a string** — Redis hashes have no numeric types. Cast before doing math.

```python
import redis

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

pipe = r.pipeline()
symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
for sym in symbols:
    pipe.hgetall(f"livebar:{sym}:1m")
raw = pipe.execute()

live = {
    sym: {"t": int(h["t"]), "close": float(h["c"]), "closed": h["x"] == "1"}
    for sym, h in zip(symbols, raw) if h
}
```

---

## 3. Redis — `kline:{SYMBOL}:1m` (closed rolling window)

The last 200 **already-closed** 1m bars, kept in strict order for fast market-wide feature pulls. **Only exists for `1m`** — for a rolling window of a coarser interval, query ClickHouse instead (it's cheap; ClickHouse handles that fine).

- **Key**: `kline:{SYMBOL}:1m`, symbol uppercase
- **Type**: Redis `List`, fixed length 200
- **Order**: **newest first** — index `0` is the most recently closed bar, index `199` is the oldest.
- **Element format**: a compact, *keyless* 10-element JSON array (not an object — saves memory and Python parse time):

| Array index | Field | Type |
| :--- | :--- | :--- |
| `[0]` | `start_time` (epoch ms, UTC) | `int` |
| `[1]` | `open` | `float` |
| `[2]` | `high` | `float` |
| `[3]` | `low` | `float` |
| `[4]` | `close` | `float` |
| `[5]` | `volume` | `float` |
| `[6]` | `quote_volume` | `float` |
| `[7]` | `taker_buy_volume` | `float` |
| `[8]` | `taker_buy_quote_volume` | `float` |
| `[9]` | `trades_count` | `int` |

```python
import redis, json

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)

# One symbol
raw_bars = r.lrange("kline:BTCUSDT:1m", 0, 199)      # newest -> oldest
bars = [json.loads(b) for b in raw_bars]
latest_close = bars[0][4]
latest_trades = bars[0][9]

# Whole market, one network round trip (the recommended pattern)
universe = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]           # get this from your own universe source
pipe = r.pipeline()
for sym in universe:
    pipe.lrange(f"kline:{sym}:1m", 0, 199)
batch = pipe.execute()

market = {sym: [json.loads(b) for b in raw] for sym, raw in zip(universe, batch)}
```

A symbol that just cold-started (new listing, or the service just came back from a long outage) may briefly have fewer than 200 entries — check `len(bars)` before assuming a full window.

**How this lines up with ClickHouse**: this array, `livebar`'s hash, and the ClickHouse row are all built from the exact same decoded event (`dispatcher.KlineEvent.toCompactBar` / `.toLiveBar` / `.toRow` each parse it once — no independent re-parsing, so values that appear in more than one place are guaranteed identical). But the *field sets* aren't identical — ClickHouse is the superset:

| Field | ClickHouse row | This array | `livebar` hash |
| :--- | :---: | :---: | :---: |
| `start_time` | ✅ | ✅ `[0]` | ✅ `t` |
| `end_time` | ✅ | ❌ | ❌ |
| OHLC | ✅ | ✅ `[1..4]` | ✅ `o/h/l/c` |
| `volume` / `quote_volume` | ✅ | ✅ `[5..6]` | ✅ `v/qv` |
| `taker_buy_volume` / `_quote_volume` | ✅ | ✅ `[7..8]` | ✅ `tbv/tbqv` |
| `trades_count` | ✅ | ✅ `[9]` | ✅ `n` |
| is-final flag | n/a (CH only ever stores closed bars) | n/a | ✅ `x` |

The only column ClickHouse has that neither Redis structure carries is `end_time` — it's omitted on purpose (nothing needs it to align or dedupe a bar; `start_time` is the sole key everywhere). If you need `end_time`, go to ClickHouse.

---

## 4. Redis — `stream:market:kline_ready` (cross-section ready notification)

A single Redis Stream that announces "every symbol's bar for this period just closed (or a timeout fallback fired) — go pull the data." This is a **trigger**, not a data payload — it never carries OHLCV, only metadata telling you where to go look.

- **Key**: `stream:market:kline_ready` (fixed name, not per-symbol)
- **Type**: Redis `Stream`, capped at `MAXLEN ~ 10000` (approximate trim, oldest entries age out)

| Field | Type | Meaning |
| :--- | :--- | :--- |
| `interval` | `string` | Which interval just closed: `"1m"` (published natively, every minute) or a coarser one from `serve_intervals` (`"5m"`, `"15m"`, `"1h"`, `"4h"`, `"1d"` — derived and forwarded once that coarser bucket's underlying 1m cross-section is ready). |
| `timestamp` | `int64` (as string) | The closed bar's open time, epoch ms UTC — same value as `start_time`/array `[0]`/hash `t` for that bar. |
| `symbols_count` | `int` (as string) | How many symbols actually landed in this cross-section. Compare against your own universe size to gauge coverage. |

**How the derived (coarser-interval) events are actually produced** — this only matters if you consume anything other than `"1m"` off this stream, but it's easy to misread, so spelled out:

1. The aggregator tracks arrivals purely at `1m` granularity. When a `1m` cross-section completes (or times out), it publishes the base `interval="1m"` event first.
2. **Only if that base publish actually went out** (i.e. it wasn't suppressed — see the gate warning below) does it check every configured coarser interval for whether *this* `1m` bar's close lines up with *that* interval's own bucket boundary (`(open_time + 60_000) % interval_ms == 0`). Each one that lines up gets its own, separate `kline_ready` entry with `interval` set accordingly.
3. **`symbols_count` on a derived event is not independently computed for that coarser bucket** — it's carried over verbatim from the `1m` section that triggered it. A `"1h"` event's `symbols_count` tells you how many symbols reported in the *last minute* of that hour, not how many symbols have a complete `1h` bar. In practice these numbers usually match, but treat it as a proxy, not an exact coarser-interval coverage count — if you need the real thing, count rows yourself: `SELECT count() FROM market.fapi_kline_1h FINAL WHERE start_time = <bucket_start>`.
4. A direct consequence of step 2: if the base `1m` publish for a bar is suppressed, **every derived interval that bar would have closed is silently skipped too** — a suppressed `1m` minute that happens to also be an hour boundary means that hour's `kline_ready` never fires either, not just the minute's.

```python
import redis

r = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
last_id = "$"   # "$" = only events from now on; use "0" to replay everything still in the stream

while True:
    resp = r.xread({"stream:market:kline_ready": last_id}, block=0, count=1)
    for _stream, entries in resp:
        for entry_id, fields in entries:
            last_id = entry_id
            interval = fields["interval"]
            ts = int(fields["timestamp"])
            n = int(fields["symbols_count"])
            print(f"cross-section ready: interval={interval} ts={ts} symbols={n}")

            if interval == "1m":
                # pull the market-wide closed window from Redis (fast path)
                ...
            else:
                # coarser interval -> query ClickHouse market.fapi_kline_<interval> FINAL
                # WHERE start_time = <ts as UTC datetime>
                ...
```

> ⚠️ **This is a best-effort hint, not a guaranteed delivery log.** While the collector is re-syncing a symbol from history (right after a restart, or after a brief network drop on one shard), `kline_ready` for the whole `1m` interval is suppressed for however long that resync takes — a few seconds on a healthy shard reconnect, up to a few minutes right after a full-process restart. Missed events are **not retried or backfilled**; nothing publishes them late. If your consumer needs a guaranteed "did this period actually close" signal rather than a low-latency nudge, poll ClickHouse or the Redis window directly instead of relying solely on this stream. See `todo_improvement/cold-start-gate-batch-latency.md` in the repo if you want the full mechanism.

---

## Field & Timestamp Conventions (apply everywhere)

- **Everything is UTC.** ClickHouse `start_time`/`end_time` are `DateTime64(3,'UTC')`; every millisecond epoch value in Redis (`t`, array `[0]`, stream `timestamp`) is also UTC-referenced (epoch is timezone-agnostic, but treat it as UTC when converting to a wall-clock date).
- **Redis never returns numbers.** Hash fields, stream fields, and the numbers inside the compact JSON array all need an explicit cast in Python (`float()`/`int()`) — `redis-py`'s `decode_responses=True` gives you strings, not typed values, for everything except the JSON array's own numeric literals (those decode as real `int`/`float` via `json.loads`).
- **`1m` is the only interval Redis knows about.** `livebar:*` and `kline:*` only ever exist as `...:1m` — there is no `livebar:BTCUSDT:5m`. Anything coarser lives in ClickHouse only.
- **ClickHouse read pattern is always `... FROM market.fapi_kline_<interval> FINAL WHERE ...`.** Forgetting `FINAL` is the single most common mistake — you'll occasionally see duplicate rows for the same `(symbol, start_time)`.
- **`start_time` is the join key everywhere** — across ClickHouse, the Redis List's `[0]`, and the Redis Hash's `t`, the same bar carries the identical epoch-ms value. Use it to align a market-wide cross-section.

---

## Where to Go Next

| Need | Document |
| :--- | :--- |
| How this data is actually produced internally (goroutines, concurrency, Go structs) | [`DATA_FLOW_AND_STRUCTURES.md`](DATA_FLOW_AND_STRUCTURES.md) |
| Deploying / operating the producer itself | [`OPERATIONS.md`](OPERATIONS.md) |
| Validating that these sources are healthy and complete before you trust them | [`../cmd/test-tools/README.md`](../cmd/test-tools/README.md) — in particular `check_redis_livebars.py`, `check_redis_closed_windows.py`, and `check_vs_binance.py` exercise exactly the reads described in this guide |
| Module-by-module architecture | [`ARCHITECTURE_MODULES.md`](ARCHITECTURE_MODULES.md) |
