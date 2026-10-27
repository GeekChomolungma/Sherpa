# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.3134**; upper quartile: **0.3266**.
- IR-spread upper quartile: **0.0921**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **0**
- Conditional: **0**
- Stable: **0**
- Mixed / Moderate: **1**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Dimension-level classification counts

- Regime-Reversal: **0**
- Conditional: **0**
- Stable: **1**
- Mixed / Moderate: **3**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 2 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3497, t=8.82) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2623, t=7.35) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3114, t=8.09) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3396, t=8.24) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3054, t=9.88) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2641, t=5.89) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3154, t=6.24) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2824, t=9.66) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3457, t=7.97) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3223, t=10.75) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2162, t=4.20) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3177, t=9.33) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lstm_v5 | volatility | Mixed / Moderate | 0.1061 | low | 0.3223 | 982 | False |
| 2 | custom.ml_lstm_v5 | dispersion | Mixed / Moderate | 0.0875 | low | 0.3497 | 677 | False |
| 3 | custom.ml_lstm_v5 | liquidity | Mixed / Moderate | 0.0755 | starved | 0.3396 | 563 | False |
| 4 | custom.ml_lstm_v5 | trend | Stable | 0.0634 | bull | 0.3457 | 532 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lstm_v5 | dispersion | low | 0.3497 | 0.3497 | original | 677 | 0.6248 |
| 2 | custom.ml_lstm_v5 | trend | bull | 0.3457 | 0.3457 | original | 532 | 0.6165 |
| 3 | custom.ml_lstm_v5 | liquidity | starved | 0.3396 | 0.3396 | original | 563 | 0.6181 |
| 4 | custom.ml_lstm_v5 | volatility | low | 0.3223 | 0.3223 | original | 982 | 0.6222 |
| 5 | custom.ml_lstm_v5 | volatility | high | 0.3177 | 0.3177 | original | 857 | 0.6208 |
| 6 | custom.ml_lstm_v5 | trend | bear | 0.3154 | 0.3154 | original | 383 | 0.6110 |
| 7 | custom.ml_lstm_v5 | dispersion | high | 0.3114 | 0.3114 | original | 661 | 0.6082 |
| 8 | custom.ml_lstm_v5 | liquidity | normal | 0.3054 | 0.3054 | original | 1065 | 0.6160 |
| 9 | custom.ml_lstm_v5 | trend | neutral | 0.2824 | 0.2824 | original | 1280 | 0.6109 |
| 10 | custom.ml_lstm_v5 | liquidity | high | 0.2641 | 0.2641 | original | 567 | 0.5996 |
| 11 | custom.ml_lstm_v5 | dispersion | normal | 0.2623 | 0.2623 | original | 857 | 0.6056 |
| 12 | custom.ml_lstm_v5 | volatility | normal | 0.2162 | 0.2162 | original | 356 | 0.5646 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
