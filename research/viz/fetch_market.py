"""从 ClickHouse 取画图用的市场背景序列（默认 BTCUSDT 的收盘价），存到 `research/viz/market/<symbol>_<interval>.csv`。

    CH_HOST=... CH_PASSWORD=... python research/viz/fetch_market.py              # BTCUSDT
    CH_HOST=... CH_PASSWORD=... python research/viz/fetch_market.py ETHUSDT      # 别的币

只是画图的背景，不进 runs（runs 只放研究线自己的产出）。时间范围 = `research/research_config.json` 的研究段
（`research_start` ~ `research_end`），**不取 holdout 段**——研究结论定下来之前不看那段行情。
时间戳是 K 线的起点（跟 runs 里的逐期序列同一个口径），收盘价在这根 K 线结束时才知道。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import clickhouse_connect
import pandas as pd

from sherpa.data.ch_reader import CHReader

ROOT = Path(__file__).resolve().parents[1]
MARKET_DIR = Path(__file__).resolve().parent / "market"


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise SystemExit(f"缺环境变量 {name}（ClickHouse 连接）")
    return value


def main(argv: list[str] | None = None) -> None:
    window = json.loads((ROOT / "research_config.json").read_text(encoding="utf-8"))["window"]
    parser = argparse.ArgumentParser(description="取画图用的市场背景序列（收盘价）")
    parser.add_argument("symbol", nargs="?", default="BTCUSDT")
    parser.add_argument("--interval", default=window["interval"])
    args = parser.parse_args(argv)

    database = os.environ.get("CH_DATABASE", "market")
    client = clickhouse_connect.get_client(
        host=_env("CH_HOST"), port=int(os.environ.get("CH_PORT", "8123")),
        username=os.environ.get("CH_USER", "default"), password=os.environ.get("CH_PASSWORD", ""), database=database,
    )
    start, end = window["research_start"], window["research_end"]
    frame = CHReader(client, database=database).fetch_history([args.symbol], args.interval, start_time=start, end_time=end)
    if frame.empty:
        raise SystemExit(f"ClickHouse 里没有 {args.symbol} {args.interval} 在 {start} ~ {end} 的数据")
    close = frame.set_index(pd.to_datetime(frame["start_time"], utc=True))["close"].astype(float)
    close = close[~close.index.duplicated(keep="last")].sort_index()
    close.index.name = "time"
    MARKET_DIR.mkdir(parents=True, exist_ok=True)
    path = MARKET_DIR / f"{args.symbol}_{args.interval}.csv"
    close.to_frame("close").to_csv(path)
    print(f"{args.symbol} {args.interval}：{len(close)} 根，{close.index[0]} ~ {close.index[-1]}，"
          f"收盘价 {close.iloc[0]:,.2f} → {close.iloc[-1]:,.2f} -> {path}")


if __name__ == "__main__":
    main()
