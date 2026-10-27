# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1488**; upper quartile: **0.1652**.
- IR-spread upper quartile: **0.1249**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **0**
- Conditional: **1**
- Stable: **0**
- Mixed / Moderate: **0**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Dimension-level classification counts

- Regime-Reversal: **0**
- Conditional: **1**
- Stable: **0**
- Mixed / Moderate: **3**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 2 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.2201, t=5.61) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1042, t=2.93) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1248, t=3.25) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1844, t=4.59) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1521, t=4.91) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.0965, t=2.26) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1475, t=2.56) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1410, t=5.34) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1588, t=3.75) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1857, t=6.25) | - | - |
| volatility | normal | 356 | False | 0/1 | - | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lstm_v5_win60_seq42` (IR=0.1500, t=4.49) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lstm_v5_win60_seq42 | volatility | Conditional | 0.1518 | low | 0.1857 | 982 | False |
| 2 | custom.ml_lstm_v5_win60_seq42 | dispersion | Mixed / Moderate | 0.1159 | low | 0.2201 | 677 | False |
| 3 | custom.ml_lstm_v5_win60_seq42 | liquidity | Mixed / Moderate | 0.0879 | starved | 0.1844 | 563 | False |
| 4 | custom.ml_lstm_v5_win60_seq42 | trend | Mixed / Moderate | 0.0177 | bull | 0.1588 | 532 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lstm_v5_win60_seq42 | dispersion | low | 0.2201 | 0.2201 | original | 677 | 0.5894 |
| 2 | custom.ml_lstm_v5_win60_seq42 | volatility | low | 0.1857 | 0.1857 | original | 982 | 0.5754 |
| 3 | custom.ml_lstm_v5_win60_seq42 | liquidity | starved | 0.1844 | 0.1844 | original | 563 | 0.5879 |
| 4 | custom.ml_lstm_v5_win60_seq42 | trend | bull | 0.1588 | 0.1588 | original | 532 | 0.5714 |
| 5 | custom.ml_lstm_v5_win60_seq42 | liquidity | normal | 0.1521 | 0.1521 | original | 1065 | 0.5700 |
| 6 | custom.ml_lstm_v5_win60_seq42 | volatility | high | 0.1500 | 0.1500 | original | 857 | 0.5811 |
| 7 | custom.ml_lstm_v5_win60_seq42 | trend | bear | 0.1475 | 0.1475 | original | 383 | 0.5901 |
| 8 | custom.ml_lstm_v5_win60_seq42 | trend | neutral | 0.1410 | 0.1410 | original | 1280 | 0.5625 |
| 9 | custom.ml_lstm_v5_win60_seq42 | dispersion | high | 0.1248 | 0.1248 | original | 661 | 0.5552 |
| 10 | custom.ml_lstm_v5_win60_seq42 | dispersion | normal | 0.1042 | 0.1042 | original | 857 | 0.5648 |
| 11 | custom.ml_lstm_v5_win60_seq42 | liquidity | high | 0.0965 | 0.0965 | original | 567 | 0.5503 |
| 12 | custom.ml_lstm_v5_win60_seq42 | volatility | normal | 0.0339 | 0.0339 | original | 356 | 0.5253 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
