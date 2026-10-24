# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.2135**; upper quartile: **0.2526**.
- IR-spread upper quartile: **0.0946**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2568, t=6.64) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1806, t=5.33) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2212, t=5.49) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2519, t=6.13) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2265, t=7.51) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1603, t=3.65) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1695, t=3.66) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2058, t=6.87) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2730, t=5.98) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2548, t=8.90) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1924, t=4.07) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1811, t=5.16) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v3 | trend | Conditional | 0.1035 | bull | 0.2730 | 532 | False |
| 2 | custom.ml_lgbm_v3 | liquidity | Mixed / Moderate | 0.0916 | starved | 0.2519 | 563 | False |
| 3 | custom.ml_lgbm_v3 | dispersion | Mixed / Moderate | 0.0761 | low | 0.2568 | 677 | False |
| 4 | custom.ml_lgbm_v3 | volatility | Mixed / Moderate | 0.0737 | low | 0.2548 | 982 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v3 | trend | bull | 0.2730 | 0.2730 | original | 532 | 0.6165 |
| 2 | custom.ml_lgbm_v3 | dispersion | low | 0.2568 | 0.2568 | original | 677 | 0.5894 |
| 3 | custom.ml_lgbm_v3 | volatility | low | 0.2548 | 0.2548 | original | 982 | 0.6090 |
| 4 | custom.ml_lgbm_v3 | liquidity | starved | 0.2519 | 0.2519 | original | 563 | 0.5950 |
| 5 | custom.ml_lgbm_v3 | liquidity | normal | 0.2265 | 0.2265 | original | 1065 | 0.5840 |
| 6 | custom.ml_lgbm_v3 | dispersion | high | 0.2212 | 0.2212 | original | 661 | 0.5930 |
| 7 | custom.ml_lgbm_v3 | trend | neutral | 0.2058 | 0.2058 | original | 1280 | 0.5773 |
| 8 | custom.ml_lgbm_v3 | volatility | normal | 0.1924 | 0.1924 | original | 356 | 0.5730 |
| 9 | custom.ml_lgbm_v3 | volatility | high | 0.1811 | 0.1811 | original | 857 | 0.5589 |
| 10 | custom.ml_lgbm_v3 | dispersion | normal | 0.1806 | 0.1806 | original | 857 | 0.5718 |
| 11 | custom.ml_lgbm_v3 | trend | bear | 0.1695 | 0.1695 | original | 383 | 0.5587 |
| 12 | custom.ml_lgbm_v3 | liquidity | high | 0.1603 | 0.1603 | original | 567 | 0.5714 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
