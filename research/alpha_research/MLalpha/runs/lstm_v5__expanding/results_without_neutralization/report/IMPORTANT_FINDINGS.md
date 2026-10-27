# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.3281**; upper quartile: **0.3355**.
- IR-spread upper quartile: **0.0892**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3577, t=9.25) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.2739, t=7.86) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3276, t=8.61) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3385, t=8.46) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3201, t=10.65) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.2831, t=6.26) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3328, t=6.61) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.2884, t=10.23) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3688, t=8.69) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3345, t=11.53) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.2289, t=4.52) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lstm_v5_expanding` (IR=0.3286, t=9.86) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lstm_v5_expanding | volatility | Mixed / Moderate | 0.1057 | low | 0.3345 | 982 | False |
| 2 | custom.ml_lstm_v5_expanding | dispersion | Mixed / Moderate | 0.0837 | low | 0.3577 | 677 | False |
| 3 | custom.ml_lstm_v5_expanding | trend | Mixed / Moderate | 0.0804 | bull | 0.3688 | 532 | False |
| 4 | custom.ml_lstm_v5_expanding | liquidity | Mixed / Moderate | 0.0555 | starved | 0.3385 | 563 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lstm_v5_expanding | trend | bull | 0.3688 | 0.3688 | original | 532 | 0.6391 |
| 2 | custom.ml_lstm_v5_expanding | dispersion | low | 0.3577 | 0.3577 | original | 677 | 0.6366 |
| 3 | custom.ml_lstm_v5_expanding | liquidity | starved | 0.3385 | 0.3385 | original | 563 | 0.6217 |
| 4 | custom.ml_lstm_v5_expanding | volatility | low | 0.3345 | 0.3345 | original | 982 | 0.6344 |
| 5 | custom.ml_lstm_v5_expanding | trend | bear | 0.3328 | 0.3328 | original | 383 | 0.6319 |
| 6 | custom.ml_lstm_v5_expanding | volatility | high | 0.3286 | 0.3286 | original | 857 | 0.6266 |
| 7 | custom.ml_lstm_v5_expanding | dispersion | high | 0.3276 | 0.3276 | original | 661 | 0.6188 |
| 8 | custom.ml_lstm_v5_expanding | liquidity | normal | 0.3201 | 0.3201 | original | 1065 | 0.6263 |
| 9 | custom.ml_lstm_v5_expanding | trend | neutral | 0.2884 | 0.2884 | original | 1280 | 0.6117 |
| 10 | custom.ml_lstm_v5_expanding | liquidity | high | 0.2831 | 0.2831 | original | 567 | 0.6138 |
| 11 | custom.ml_lstm_v5_expanding | dispersion | normal | 0.2739 | 0.2739 | original | 857 | 0.6126 |
| 12 | custom.ml_lstm_v5_expanding | volatility | normal | 0.2289 | 0.2289 | original | 356 | 0.5758 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
