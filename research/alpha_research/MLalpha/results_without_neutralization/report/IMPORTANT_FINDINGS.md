# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **24**; factors: **2**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1970**; upper quartile: **0.2252**.
- IR-spread upper quartile: **0.1192**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **0**
- Conditional: **2**
- Stable: **0**
- Mixed / Moderate: **0**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Dimension-level classification counts

- Regime-Reversal: **0**
- Conditional: **2**
- Stable: **2**
- Mixed / Moderate: **4**
- Weak / Noise: **0**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 2 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 677 | False | 2/2 | `+custom.ml_lgbm_v1` (IR=0.2476, t=6.09) | `+custom.ml_lgbm_v2` (IR=0.2394, t=6.22) | - |
| dispersion | normal | 857 | False | 2/2 | `+custom.ml_lgbm_v1` (IR=0.1817, t=5.40) | `+custom.ml_lgbm_v2` (IR=0.1778, t=5.14) | - |
| dispersion | high | 661 | False | 2/2 | `+custom.ml_lgbm_v2` (IR=0.1987, t=5.23) | `+custom.ml_lgbm_v1` (IR=0.1489, t=4.15) | - |
| liquidity | starved | 563 | False | 2/2 | `+custom.ml_lgbm_v1` (IR=0.2298, t=5.53) | `+custom.ml_lgbm_v2` (IR=0.2180, t=5.24) | - |
| liquidity | normal | 1065 | False | 2/2 | `+custom.ml_lgbm_v2` (IR=0.2236, t=7.36) | `+custom.ml_lgbm_v1` (IR=0.1633, t=5.37) | - |
| liquidity | high | 567 | False | 2/2 | `+custom.ml_lgbm_v1` (IR=0.2056, t=5.34) | `+custom.ml_lgbm_v2` (IR=0.1503, t=3.34) | - |
| trend | bear | 383 | False | 2/2 | `+custom.ml_lgbm_v2` (IR=0.1149, t=2.28) | `+custom.ml_lgbm_v1` (IR=0.1105, t=2.20) | - |
| trend | neutral | 1280 | False | 2/2 | `+custom.ml_lgbm_v2` (IR=0.1940, t=6.88) | `+custom.ml_lgbm_v1` (IR=0.1722, t=6.36) | - |
| trend | bull | 532 | False | 2/2 | `+custom.ml_lgbm_v1` (IR=0.2863, t=7.05) | `+custom.ml_lgbm_v2` (IR=0.2847, t=6.57) | - |
| volatility | low | 982 | False | 2/2 | `+custom.ml_lgbm_v2` (IR=0.2155, t=7.18) | `+custom.ml_lgbm_v1` (IR=0.2146, t=7.16) | - |
| volatility | normal | 356 | False | 2/2 | `+custom.ml_lgbm_v2` (IR=0.2474, t=4.63) | `+custom.ml_lgbm_v1` (IR=0.1123, t=2.37) | - |
| volatility | high | 857 | False | 2/2 | `+custom.ml_lgbm_v1` (IR=0.1953, t=6.02) | `+custom.ml_lgbm_v2` (IR=0.1692, t=4.92) | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v1 | trend | Conditional | 0.1759 | bull | 0.2863 | 532 | False |
| 2 | custom.ml_lgbm_v2 | trend | Conditional | 0.1698 | bull | 0.2847 | 532 | False |
| 3 | custom.ml_lgbm_v1 | volatility | Mixed / Moderate | 0.1023 | low | 0.2146 | 982 | False |
| 4 | custom.ml_lgbm_v1 | dispersion | Mixed / Moderate | 0.0987 | low | 0.2476 | 677 | False |
| 5 | custom.ml_lgbm_v2 | volatility | Mixed / Moderate | 0.0782 | normal | 0.2474 | 356 | False |
| 6 | custom.ml_lgbm_v2 | liquidity | Mixed / Moderate | 0.0733 | normal | 0.2236 | 1065 | False |
| 7 | custom.ml_lgbm_v1 | liquidity | Stable | 0.0665 | starved | 0.2298 | 563 | False |
| 8 | custom.ml_lgbm_v2 | dispersion | Stable | 0.0616 | low | 0.2394 | 677 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v1 | trend | bull | 0.2863 | 0.2863 | original | 532 | 0.6147 |
| 2 | custom.ml_lgbm_v2 | trend | bull | 0.2847 | 0.2847 | original | 532 | 0.6128 |
| 3 | custom.ml_lgbm_v1 | dispersion | low | 0.2476 | 0.2476 | original | 677 | 0.5775 |
| 4 | custom.ml_lgbm_v2 | volatility | normal | 0.2474 | 0.2474 | original | 356 | 0.5899 |
| 5 | custom.ml_lgbm_v2 | dispersion | low | 0.2394 | 0.2394 | original | 677 | 0.5835 |
| 6 | custom.ml_lgbm_v1 | liquidity | starved | 0.2298 | 0.2298 | original | 563 | 0.5879 |
| 7 | custom.ml_lgbm_v2 | liquidity | normal | 0.2236 | 0.2236 | original | 1065 | 0.5972 |
| 8 | custom.ml_lgbm_v2 | liquidity | starved | 0.2180 | 0.2180 | original | 563 | 0.5844 |
| 9 | custom.ml_lgbm_v2 | volatility | low | 0.2155 | 0.2155 | original | 982 | 0.5957 |
| 10 | custom.ml_lgbm_v1 | volatility | low | 0.2146 | 0.2146 | original | 982 | 0.5723 |
| 11 | custom.ml_lgbm_v1 | liquidity | high | 0.2056 | 0.2056 | original | 567 | 0.5802 |
| 12 | custom.ml_lgbm_v2 | dispersion | high | 0.1987 | 0.1987 | original | 661 | 0.5764 |
| 13 | custom.ml_lgbm_v1 | volatility | high | 0.1953 | 0.1953 | original | 857 | 0.5834 |
| 14 | custom.ml_lgbm_v2 | trend | neutral | 0.1940 | 0.1940 | original | 1280 | 0.5727 |
| 15 | custom.ml_lgbm_v1 | dispersion | normal | 0.1817 | 0.1817 | original | 857 | 0.5834 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
