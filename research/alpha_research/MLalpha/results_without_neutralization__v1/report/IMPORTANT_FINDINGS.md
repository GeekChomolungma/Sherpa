# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1844**; upper quartile: **0.2079**.
- IR-spread upper quartile: **0.1235**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2341, t=5.61) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1829, t=5.54) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1294, t=3.68) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2073, t=4.97) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1521, t=5.12) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2099, t=5.41) | - | - |
| trend | bear | 383 | False | 0/1 | - | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1763, t=6.50) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2590, t=6.28) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1946, t=6.47) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1314, t=2.58) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1859, t=5.91) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v1 | trend | Conditional | 0.1799 | bull | 0.2590 | 532 | False |
| 2 | custom.ml_lgbm_v1 | dispersion | Mixed / Moderate | 0.1046 | low | 0.2341 | 677 | False |
| 3 | custom.ml_lgbm_v1 | volatility | Mixed / Moderate | 0.0632 | low | 0.1946 | 982 | False |
| 4 | custom.ml_lgbm_v1 | liquidity | Stable | 0.0578 | high | 0.2099 | 567 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v1 | trend | bull | 0.2590 | 0.2590 | original | 532 | 0.6034 |
| 2 | custom.ml_lgbm_v1 | dispersion | low | 0.2341 | 0.2341 | original | 677 | 0.5864 |
| 3 | custom.ml_lgbm_v1 | liquidity | high | 0.2099 | 0.2099 | original | 567 | 0.5820 |
| 4 | custom.ml_lgbm_v1 | liquidity | starved | 0.2073 | 0.2073 | original | 563 | 0.5790 |
| 5 | custom.ml_lgbm_v1 | volatility | low | 0.1946 | 0.1946 | original | 982 | 0.5692 |
| 6 | custom.ml_lgbm_v1 | volatility | high | 0.1859 | 0.1859 | original | 857 | 0.5834 |
| 7 | custom.ml_lgbm_v1 | dispersion | normal | 0.1829 | 0.1829 | original | 857 | 0.5869 |
| 8 | custom.ml_lgbm_v1 | trend | neutral | 0.1763 | 0.1763 | original | 1280 | 0.5734 |
| 9 | custom.ml_lgbm_v1 | liquidity | normal | 0.1521 | 0.1521 | original | 1065 | 0.5690 |
| 10 | custom.ml_lgbm_v1 | volatility | normal | 0.1314 | 0.1314 | original | 356 | 0.5702 |
| 11 | custom.ml_lgbm_v1 | dispersion | high | 0.1294 | 0.1294 | original | 661 | 0.5477 |
| 12 | custom.ml_lgbm_v1 | trend | bear | 0.0790 | 0.0790 | original | 383 | 0.5405 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
