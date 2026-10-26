# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.3278**; upper quartile: **0.3357**.
- IR-spread upper quartile: **0.0883**. This is used as the primary 'regime-sensitive' cutoff.
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
- Stable: **0**
- Mixed / Moderate: **4**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 2 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3575, t=9.25) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2748, t=7.89) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3272, t=8.60) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3383, t=8.45) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3207, t=10.67) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2827, t=6.25) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3324, t=6.61) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2886, t=10.24) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3694, t=8.71) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3348, t=11.55) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.2298, t=4.53) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lstm_v5` (IR=0.3283, t=9.87) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lstm_v5 | volatility | Mixed / Moderate | 0.1050 | low | 0.3348 | 982 | False |
| 2 | custom.ml_lstm_v5 | dispersion | Mixed / Moderate | 0.0827 | low | 0.3575 | 677 | False |
| 3 | custom.ml_lstm_v5 | trend | Mixed / Moderate | 0.0808 | bull | 0.3694 | 532 | False |
| 4 | custom.ml_lstm_v5 | liquidity | Mixed / Moderate | 0.0556 | starved | 0.3383 | 563 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lstm_v5 | trend | bull | 0.3694 | 0.3694 | original | 532 | 0.6391 |
| 2 | custom.ml_lstm_v5 | dispersion | low | 0.3575 | 0.3575 | original | 677 | 0.6352 |
| 3 | custom.ml_lstm_v5 | liquidity | starved | 0.3383 | 0.3383 | original | 563 | 0.6217 |
| 4 | custom.ml_lstm_v5 | volatility | low | 0.3348 | 0.3348 | original | 982 | 0.6365 |
| 5 | custom.ml_lstm_v5 | trend | bear | 0.3324 | 0.3324 | original | 383 | 0.6292 |
| 6 | custom.ml_lstm_v5 | volatility | high | 0.3283 | 0.3283 | original | 857 | 0.6243 |
| 7 | custom.ml_lstm_v5 | dispersion | high | 0.3272 | 0.3272 | original | 661 | 0.6188 |
| 8 | custom.ml_lstm_v5 | liquidity | normal | 0.3207 | 0.3207 | original | 1065 | 0.6272 |
| 9 | custom.ml_lstm_v5 | trend | neutral | 0.2886 | 0.2886 | original | 1280 | 0.6125 |
| 10 | custom.ml_lstm_v5 | liquidity | high | 0.2827 | 0.2827 | original | 567 | 0.6120 |
| 11 | custom.ml_lstm_v5 | dispersion | normal | 0.2748 | 0.2748 | original | 857 | 0.6138 |
| 12 | custom.ml_lstm_v5 | volatility | normal | 0.2298 | 0.2298 | original | 356 | 0.5758 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
