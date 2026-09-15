> **Language:** English | [简体中文](README.zh-CN.md)

# Sherpa

Sherpa is a **data-to-signal engine** for crypto quantitative research: it turns ClickHouse/Redis market data into standardized trading signals (`SignalIntent`), through the same strategy code whether you're backtesting or running live. The goal is to grow this into a full **backtest-research + live-signal strategy library** — it is not there yet (see [Project Status](#project-status) below).

Order execution, position reconciliation, and fund settlement are explicitly out of scope — that belongs to a downstream execution service ("Webhooker"). Sherpa stops at generating the signal.

## What's here

| Layer | Package | Role |
| :-- | :-- | :-- |
| Data | `sherpa.data` | `BarPanel`/`MarketEvent` contracts, ClickHouse/Redis readers, the `IPanelSource` abstraction shared by backtest and live |
| Alpha | `sherpa.alpha` | `Alpha` base class, `AlphaEngine`, three families: WorldQuant (101/101 formulas implemented), TradingView, custom |
| Shared tools | `sherpa.portfolio`, `sherpa.metrics` | Pure functions: alpha→weight mapping, turnover, RankIC/IC_IR, Sharpe/Calmar/MaxDrawdown — reusable by research, backtest, and (eventually) live |
| Backtest | `sherpa.backtest` | Two-layer evaluation (see `docs/backtest_principle.md`): `alpha_check`/`screening` (statistical pass/fail) and `vectorized`/`event_driven` (portfolio simulation with costs) |
| Strategy | `sherpa.strategy` | `BaseStrategy`, `Runner` (one main loop for both backtest and live), and the `sink/` adapters (`LogSink`, `BacktestSink`, `WebhookSink`) |
| Live | `sherpa.live` | Dispatch-time formatting (idempotency keys, timestamps) for whatever sink is attached — no decision logic lives here |

Full design reference: [`docs/SHERPA_DESIGN.md`](docs/SHERPA_DESIGN.md). Upstream data contract: [`docs/DATA_CONSUMER_GUIDE.md`](docs/DATA_CONSUMER_GUIDE.md).

## Repository layout

```text
sherpa/       library code (see table above)
tests/        unit tests, mirrors sherpa/ layout
examples/     runnable teaching scripts against synthetic data
research/     real research projects against live ClickHouse data
  worldquant_101/   batch-screening + per-category vectorized backtests for the WorldQuant 101 library
docs/         design docs
scripts/      one-off ops scripts (e.g. a ClickHouse/Redis smoke test)
```

## Getting started

```bash
pip install -e ".[dev]"
pytest                              # run the test suite
python examples/vectorized_research.py   # a self-contained example on synthetic data
```

`research/` scripts need a real ClickHouse connection via environment variables (`CH_HOST`, `CH_PORT`, `CH_USER`, `CH_PASSWORD`, `CH_DATABASE`) — see the docstring at the top of each script.

## Project status

This is a working framework, not a finished product. Honest state as of now:

- **Data layer** — done, smoke-tested against real ClickHouse/Redis.
- **Alpha library** — all 101 WorldQuant formulas are implemented and registered (19 are intentional no-ops: they need industry-classification or market-cap data the current `BarPanel` doesn't carry). Only **2** TradingView indicators exist so far. Most of the 101 factors have **not** been validated against real market data yet — that validation work lives in `research/worldquant_101/` and is in progress, not finished.
- **Backtest engine** — the two-layer pipeline (`alpha_check`/`screening` → `vectorized`/`event_driven`) works and is unit-tested, but the *research workflow* around it (multi-factor combination, parameter sensitivity, standardized reporting) is still minimal — right now it's "call the functions yourself," not a polished tool.
- **Strategy/Runner/sink** — `BaseStrategy`, `Runner`, `LogSink`, and `BacktestSink` are implemented and tested end to end in `examples/`. A real strategy built on validated alphas, run through the full backtest→sink pipeline, hasn't been done yet.
- **Live signal path** — `WebhookSink` is a placeholder that raises on use; there is no real execution-service integration. Position-rebalancing/risk-gating logic (deliberately) hasn't been designed yet — see `docs/SHERPA_DESIGN.md` §8 for the reasoning.

In short: the plumbing is solid, the alpha research is early, and the live path doesn't exist yet.

## License

Not yet decided.
