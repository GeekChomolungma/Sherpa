# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1826**; upper quartile: **0.1942**.
- IR-spread upper quartile: **0.1292**. This is used as the primary 'regime-sensitive' cutoff.
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
- Stable: **1**
- Mixed / Moderate: **2**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 2 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.2616, t=6.88) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1264, t=3.63) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1465, t=3.69) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.2333, t=5.84) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1796, t=5.96) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1062, t=2.59) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1917, t=3.68) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1620, t=6.12) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1936, t=4.77) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1960, t=6.59) | - | - |
| volatility | normal | 356 | False | 0/1 | - | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lstm_v5_win60` (IR=0.1856, t=5.55) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lstm_v5_win60 | dispersion | Conditional | 0.1352 | low | 0.2616 | 677 | False |
| 2 | custom.ml_lstm_v5_win60 | liquidity | Mixed / Moderate | 0.1272 | starved | 0.2333 | 563 | False |
| 3 | custom.ml_lstm_v5_win60 | volatility | Mixed / Moderate | 0.1059 | low | 0.1960 | 982 | False |
| 4 | custom.ml_lstm_v5_win60 | trend | Stable | 0.0317 | bull | 0.1936 | 532 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lstm_v5_win60 | dispersion | low | 0.2616 | 0.2616 | original | 677 | 0.6041 |
| 2 | custom.ml_lstm_v5_win60 | liquidity | starved | 0.2333 | 0.2333 | original | 563 | 0.6092 |
| 3 | custom.ml_lstm_v5_win60 | volatility | low | 0.1960 | 0.1960 | original | 982 | 0.5754 |
| 4 | custom.ml_lstm_v5_win60 | trend | bull | 0.1936 | 0.1936 | original | 532 | 0.5677 |
| 5 | custom.ml_lstm_v5_win60 | trend | bear | 0.1917 | 0.1917 | original | 383 | 0.5822 |
| 6 | custom.ml_lstm_v5_win60 | volatility | high | 0.1856 | 0.1856 | original | 857 | 0.5823 |
| 7 | custom.ml_lstm_v5_win60 | liquidity | normal | 0.1796 | 0.1796 | original | 1065 | 0.5634 |
| 8 | custom.ml_lstm_v5_win60 | trend | neutral | 0.1620 | 0.1620 | original | 1280 | 0.5734 |
| 9 | custom.ml_lstm_v5_win60 | dispersion | high | 0.1465 | 0.1465 | original | 661 | 0.5567 |
| 10 | custom.ml_lstm_v5_win60 | dispersion | normal | 0.1264 | 0.1264 | original | 857 | 0.5624 |
| 11 | custom.ml_lstm_v5_win60 | liquidity | high | 0.1062 | 0.1062 | original | 567 | 0.5573 |
| 12 | custom.ml_lstm_v5_win60 | volatility | normal | 0.0901 | 0.0901 | original | 356 | 0.5478 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
