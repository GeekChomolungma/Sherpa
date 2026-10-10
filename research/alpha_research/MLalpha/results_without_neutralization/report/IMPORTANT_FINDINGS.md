# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.2053**; upper quartile: **0.2357**.
- IR-spread upper quartile: **0.0943**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2427, t=6.33) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1863, t=5.63) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2076, t=5.15) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2333, t=5.65) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2272, t=7.50) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1537, t=3.53) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1393, t=2.94) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2030, t=6.79) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2777, t=6.09) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.2463, t=8.50) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1812, t=3.78) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lgbm_v3` (IR=0.1796, t=5.24) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v3 | trend | Conditional | 0.1384 | bull | 0.2777 | 532 | False |
| 2 | custom.ml_lgbm_v3 | liquidity | Mixed / Moderate | 0.0796 | starved | 0.2333 | 563 | False |
| 3 | custom.ml_lgbm_v3 | volatility | Mixed / Moderate | 0.0667 | low | 0.2463 | 982 | False |
| 4 | custom.ml_lgbm_v3 | dispersion | Stable | 0.0564 | low | 0.2427 | 677 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v3 | trend | bull | 0.2777 | 0.2777 | original | 532 | 0.6259 |
| 2 | custom.ml_lgbm_v3 | volatility | low | 0.2463 | 0.2463 | original | 982 | 0.6130 |
| 3 | custom.ml_lgbm_v3 | dispersion | low | 0.2427 | 0.2427 | original | 677 | 0.5908 |
| 4 | custom.ml_lgbm_v3 | liquidity | starved | 0.2333 | 0.2333 | original | 563 | 0.5879 |
| 5 | custom.ml_lgbm_v3 | liquidity | normal | 0.2272 | 0.2272 | original | 1065 | 0.5915 |
| 6 | custom.ml_lgbm_v3 | dispersion | high | 0.2076 | 0.2076 | original | 661 | 0.5825 |
| 7 | custom.ml_lgbm_v3 | trend | neutral | 0.2030 | 0.2030 | original | 1280 | 0.5734 |
| 8 | custom.ml_lgbm_v3 | dispersion | normal | 0.1863 | 0.1863 | original | 857 | 0.5811 |
| 9 | custom.ml_lgbm_v3 | volatility | normal | 0.1812 | 0.1812 | original | 356 | 0.5787 |
| 10 | custom.ml_lgbm_v3 | volatility | high | 0.1796 | 0.1796 | original | 857 | 0.5543 |
| 11 | custom.ml_lgbm_v3 | liquidity | high | 0.1537 | 0.1537 | original | 567 | 0.5679 |
| 12 | custom.ml_lgbm_v3 | trend | bear | 0.1393 | 0.1393 | original | 383 | 0.5640 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
