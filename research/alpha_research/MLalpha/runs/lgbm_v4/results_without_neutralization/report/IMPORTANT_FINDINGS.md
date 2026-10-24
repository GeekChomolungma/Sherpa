# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.2342**; upper quartile: **0.2496**.
- IR-spread upper quartile: **0.1015**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2762, t=7.43) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1907, t=5.44) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2214, t=5.86) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2886, t=6.88) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2386, t=8.09) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1393, t=3.41) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2473, t=5.60) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2054, t=7.71) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2562, t=5.78) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2383, t=8.38) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1720, t=4.40) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2301, t=6.65) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v4 | liquidity | Conditional | 0.1493 | starved | 0.2886 | 563 | False |
| 2 | custom.ml_lgbm_v4 | dispersion | Mixed / Moderate | 0.0855 | low | 0.2762 | 677 | False |
| 3 | custom.ml_lgbm_v4 | volatility | Mixed / Moderate | 0.0664 | low | 0.2383 | 982 | False |
| 4 | custom.ml_lgbm_v4 | trend | Stable | 0.0509 | bull | 0.2562 | 532 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v4 | liquidity | starved | 0.2886 | 0.2886 | original | 563 | 0.5950 |
| 2 | custom.ml_lgbm_v4 | dispersion | low | 0.2762 | 0.2762 | original | 677 | 0.5923 |
| 3 | custom.ml_lgbm_v4 | trend | bull | 0.2562 | 0.2562 | original | 532 | 0.5902 |
| 4 | custom.ml_lgbm_v4 | trend | bear | 0.2473 | 0.2473 | original | 383 | 0.6031 |
| 5 | custom.ml_lgbm_v4 | liquidity | normal | 0.2386 | 0.2386 | original | 1065 | 0.6038 |
| 6 | custom.ml_lgbm_v4 | volatility | low | 0.2383 | 0.2383 | original | 982 | 0.5784 |
| 7 | custom.ml_lgbm_v4 | volatility | high | 0.2301 | 0.2301 | original | 857 | 0.6044 |
| 8 | custom.ml_lgbm_v4 | dispersion | high | 0.2214 | 0.2214 | original | 661 | 0.5779 |
| 9 | custom.ml_lgbm_v4 | trend | neutral | 0.2054 | 0.2054 | original | 1280 | 0.5750 |
| 10 | custom.ml_lgbm_v4 | dispersion | normal | 0.1907 | 0.1907 | original | 857 | 0.5811 |
| 11 | custom.ml_lgbm_v4 | volatility | normal | 0.1720 | 0.1720 | original | 356 | 0.5478 |
| 12 | custom.ml_lgbm_v4 | liquidity | high | 0.1393 | 0.1393 | original | 567 | 0.5344 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
