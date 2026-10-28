# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.2441**; upper quartile: **0.2759**.
- IR-spread upper quartile: **0.1076**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 677 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2978, t=8.29) | - | - |
| dispersion | normal | 857 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2026, t=5.43) | - | - |
| dispersion | high | 661 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2298, t=6.04) | - | - |
| liquidity | starved | 563 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2944, t=7.10) | - | - |
| liquidity | normal | 1065 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2584, t=8.70) | - | - |
| liquidity | high | 567 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.1496, t=3.69) | - | - |
| trend | bear | 383 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2843, t=6.24) | - | - |
| trend | neutral | 1280 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2102, t=7.41) | - | - |
| trend | bull | 532 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2731, t=6.20) | - | - |
| volatility | low | 982 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2630, t=9.23) | - | - |
| volatility | normal | 356 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2010, t=4.53) | - | - |
| volatility | high | 857 | False | 1/1 | `+custom.ml_xgb_v5` (IR=0.2252, t=6.58) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.ml_xgb_v5 | liquidity | Conditional | 0.1448 | starved | 0.2944 | 563 | False |
| 2 | custom.ml_xgb_v5 | dispersion | Mixed / Moderate | 0.0952 | low | 0.2978 | 677 | False |
| 3 | custom.ml_xgb_v5 | trend | Mixed / Moderate | 0.0741 | bear | 0.2843 | 383 | False |
| 4 | custom.ml_xgb_v5 | volatility | Mixed / Moderate | 0.0620 | low | 0.2630 | 982 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.ml_xgb_v5 | dispersion | low | 0.2978 | 0.2978 | original | 677 | 0.6115 |
| 2 | custom.ml_xgb_v5 | liquidity | starved | 0.2944 | 0.2944 | original | 563 | 0.6021 |
| 3 | custom.ml_xgb_v5 | trend | bear | 0.2843 | 0.2843 | original | 383 | 0.6110 |
| 4 | custom.ml_xgb_v5 | trend | bull | 0.2731 | 0.2731 | original | 532 | 0.6034 |
| 5 | custom.ml_xgb_v5 | volatility | low | 0.2630 | 0.2630 | original | 982 | 0.5988 |
| 6 | custom.ml_xgb_v5 | liquidity | normal | 0.2584 | 0.2584 | original | 1065 | 0.6085 |
| 7 | custom.ml_xgb_v5 | dispersion | high | 0.2298 | 0.2298 | original | 661 | 0.5779 |
| 8 | custom.ml_xgb_v5 | volatility | high | 0.2252 | 0.2252 | original | 857 | 0.5939 |
| 9 | custom.ml_xgb_v5 | trend | neutral | 0.2102 | 0.2102 | original | 1280 | 0.5836 |
| 10 | custom.ml_xgb_v5 | dispersion | normal | 0.2026 | 0.2026 | original | 857 | 0.5904 |
| 11 | custom.ml_xgb_v5 | volatility | normal | 0.2010 | 0.2010 | original | 356 | 0.5758 |
| 12 | custom.ml_xgb_v5 | liquidity | high | 0.1496 | 0.1496 | original | 567 | 0.5556 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
