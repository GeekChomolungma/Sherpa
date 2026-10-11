# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.2120**; upper quartile: **0.2157**.
- IR-spread upper quartile: **0.0656**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2153, t=5.64) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.1722, t=5.04) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2163, t=5.73) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2156, t=5.14) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2111, t=6.97) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.1588, t=3.44) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.1660, t=3.20) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.1838, t=6.24) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2559, t=5.97) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2129, t=7.15) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.2270, t=4.32) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_lgbm_v2` (IR=0.1696, t=5.18) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v2 | trend | Conditional | 0.0899 | bull | 0.2559 | 532 | False |
| 2 | custom.ml_lgbm_v2 | volatility | Mixed / Moderate | 0.0575 | normal | 0.2270 | 356 | False |
| 3 | custom.ml_lgbm_v2 | liquidity | Mixed / Moderate | 0.0568 | starved | 0.2156 | 563 | False |
| 4 | custom.ml_lgbm_v2 | dispersion | Stable | 0.0440 | high | 0.2163 | 661 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v2 | trend | bull | 0.2559 | 0.2559 | original | 532 | 0.5959 |
| 2 | custom.ml_lgbm_v2 | volatility | normal | 0.2270 | 0.2270 | original | 356 | 0.5702 |
| 3 | custom.ml_lgbm_v2 | dispersion | high | 0.2163 | 0.2163 | original | 661 | 0.5703 |
| 4 | custom.ml_lgbm_v2 | liquidity | starved | 0.2156 | 0.2156 | original | 563 | 0.5861 |
| 5 | custom.ml_lgbm_v2 | dispersion | low | 0.2153 | 0.2153 | original | 677 | 0.5672 |
| 6 | custom.ml_lgbm_v2 | volatility | low | 0.2129 | 0.2129 | original | 982 | 0.5845 |
| 7 | custom.ml_lgbm_v2 | liquidity | normal | 0.2111 | 0.2111 | original | 1065 | 0.5765 |
| 8 | custom.ml_lgbm_v2 | trend | neutral | 0.1838 | 0.1838 | original | 1280 | 0.5648 |
| 9 | custom.ml_lgbm_v2 | dispersion | normal | 0.1722 | 0.1722 | original | 857 | 0.5741 |
| 10 | custom.ml_lgbm_v2 | volatility | high | 0.1696 | 0.1696 | original | 857 | 0.5554 |
| 11 | custom.ml_lgbm_v2 | trend | bear | 0.1660 | 0.1660 | original | 383 | 0.5561 |
| 12 | custom.ml_lgbm_v2 | liquidity | high | 0.1588 | 0.1588 | original | 567 | 0.5450 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
