# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1249**; upper quartile: **0.1517**.
- IR-spread upper quartile: **0.0984**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 422 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1752, t=3.06) | - | - |
| dispersion | normal | 574 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.0902, t=2.12) | - | - |
| dispersion | high | 473 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1230, t=2.66) | - | - |
| liquidity | starved | 368 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.2159, t=4.54) | - | - |
| liquidity | normal | 705 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1111, t=2.60) | - | - |
| liquidity | high | 396 | False | 0/1 | - | - | - |
| trend | bear | 297 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1493, t=2.41) | - | - |
| trend | neutral | 844 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1268, t=3.55) | - | - |
| trend | bull | 328 | False | 0/1 | - | - | - |
| volatility | low | 510 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1285, t=2.57) | - | - |
| volatility | normal | 441 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.1589, t=3.39) | - | - |
| volatility | high | 518 | False | 1/1 | `+custom.ml_lgbm_v4` (IR=0.0955, t=2.03) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_lgbm_v4 | liquidity | Conditional | 0.1387 | starved | 0.2159 | 368 | False |
| 2 | custom.ml_lgbm_v4 | dispersion | Mixed / Moderate | 0.0850 | low | 0.1752 | 422 | False |
| 3 | custom.ml_lgbm_v4 | volatility | Mixed / Moderate | 0.0634 | normal | 0.1589 | 441 | False |
| 4 | custom.ml_lgbm_v4 | trend | Stable | 0.0542 | bear | 0.1493 | 297 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_lgbm_v4 | liquidity | starved | 0.2159 | 0.2159 | original | 368 | 0.5951 |
| 2 | custom.ml_lgbm_v4 | dispersion | low | 0.1752 | 0.1752 | original | 422 | 0.5782 |
| 3 | custom.ml_lgbm_v4 | volatility | normal | 0.1589 | 0.1589 | original | 441 | 0.5760 |
| 4 | custom.ml_lgbm_v4 | trend | bear | 0.1493 | 0.1493 | original | 297 | 0.5690 |
| 5 | custom.ml_lgbm_v4 | volatility | low | 0.1285 | 0.1285 | original | 510 | 0.5549 |
| 6 | custom.ml_lgbm_v4 | trend | neutral | 0.1268 | 0.1268 | original | 844 | 0.5592 |
| 7 | custom.ml_lgbm_v4 | dispersion | high | 0.1230 | 0.1230 | original | 473 | 0.5518 |
| 8 | custom.ml_lgbm_v4 | liquidity | normal | 0.1111 | 0.1111 | original | 705 | 0.5603 |
| 9 | custom.ml_lgbm_v4 | volatility | high | 0.0955 | 0.0955 | original | 518 | 0.5463 |
| 10 | custom.ml_lgbm_v4 | trend | bull | 0.0951 | 0.0951 | original | 328 | 0.5457 |
| 11 | custom.ml_lgbm_v4 | dispersion | normal | 0.0902 | 0.0902 | original | 574 | 0.5488 |
| 12 | custom.ml_lgbm_v4 | liquidity | high | 0.0772 | 0.0772 | original | 396 | 0.5202 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
