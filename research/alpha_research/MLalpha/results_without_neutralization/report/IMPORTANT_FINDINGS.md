# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.2036**; upper quartile: **0.2148**.
- IR-spread upper quartile: **0.0564**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 1399 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2152, t=7.52) | - | - |
| dispersion | normal | 1683 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1907, t=7.64) | - | - |
| dispersion | high | 1303 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2121, t=7.43) | - | - |
| liquidity | starved | 1150 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1957, t=6.19) | - | - |
| liquidity | normal | 2100 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1920, t=9.20) | - | - |
| liquidity | high | 1135 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2379, t=8.61) | - | - |
| trend | bear | 848 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1749, t=5.45) | - | - |
| trend | neutral | 2521 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1921, t=9.56) | - | - |
| trend | bull | 1016 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2627, t=9.26) | - | - |
| volatility | low | 1898 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2115, t=9.74) | - | - |
| volatility | normal | 963 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.2146, t=6.67) | - | - |
| volatility | high | 1524 | False | 1/1 | `+custom.ml_lgbm_v1` (IR=0.1906, t=7.89) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v1 | trend | Conditional | 0.0878 | bull | 0.2627 | 1016 | False |
| 2 | custom.ml_lgbm_v1 | liquidity | Mixed / Moderate | 0.0459 | high | 0.2379 | 1135 | False |
| 3 | custom.ml_lgbm_v1 | dispersion | Mixed / Moderate | 0.0246 | low | 0.2152 | 1399 | False |
| 4 | custom.ml_lgbm_v1 | volatility | Stable | 0.0240 | normal | 0.2146 | 963 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v1 | trend | bull | 0.2627 | 0.2627 | original | 1016 | 0.6093 |
| 2 | custom.ml_lgbm_v1 | liquidity | high | 0.2379 | 0.2379 | original | 1135 | 0.6035 |
| 3 | custom.ml_lgbm_v1 | dispersion | low | 0.2152 | 0.2152 | original | 1399 | 0.5797 |
| 4 | custom.ml_lgbm_v1 | volatility | normal | 0.2146 | 0.2146 | original | 963 | 0.5753 |
| 5 | custom.ml_lgbm_v1 | dispersion | high | 0.2121 | 0.2121 | original | 1303 | 0.5840 |
| 6 | custom.ml_lgbm_v1 | volatility | low | 0.2115 | 0.2115 | original | 1898 | 0.5854 |
| 7 | custom.ml_lgbm_v1 | liquidity | starved | 0.1957 | 0.1957 | original | 1150 | 0.5730 |
| 8 | custom.ml_lgbm_v1 | trend | neutral | 0.1921 | 0.1921 | original | 2521 | 0.5736 |
| 9 | custom.ml_lgbm_v1 | liquidity | normal | 0.1920 | 0.1920 | original | 2100 | 0.5714 |
| 10 | custom.ml_lgbm_v1 | dispersion | normal | 0.1907 | 0.1907 | original | 1683 | 0.5775 |
| 11 | custom.ml_lgbm_v1 | volatility | high | 0.1906 | 0.1906 | original | 1524 | 0.5768 |
| 12 | custom.ml_lgbm_v1 | trend | bear | 0.1749 | 0.1749 | original | 848 | 0.5649 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
