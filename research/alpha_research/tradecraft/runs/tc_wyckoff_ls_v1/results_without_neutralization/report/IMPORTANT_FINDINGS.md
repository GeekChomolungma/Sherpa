# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0547**; upper quartile: **0.0735**.
- IR-spread upper quartile: **0.0628**. This is used as the primary 'regime-sensitive' cutoff.
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

Only alphas with |t_stat| >= 0 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 924 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0327, t=-0.99) | - | - |
| dispersion | normal | 1177 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0874, t=-2.88) | - | - |
| dispersion | high | 875 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0363, t=-1.05) | - | - |
| liquidity | starved | 762 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0180, t=-0.51) | - | - |
| liquidity | normal | 1454 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0658, t=-2.46) | - | - |
| liquidity | high | 760 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0717, t=-2.19) | - | - |
| trend | bear | 553 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0242, t=-0.57) | - | - |
| trend | neutral | 1711 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0561, t=-2.17) | - | - |
| trend | bull | 712 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0786, t=-2.05) | - | - |
| volatility | low | 1281 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0533, t=-1.83) | - | - |
| volatility | normal | 578 | False | 1/1 | `+custom.tc_wyckoff_ls_v1` (IR=0.0005, t=0.01) | - | - |
| volatility | high | 1117 | False | 1/1 | `-custom.tc_wyckoff_ls_v1` (IR=-0.0865, t=-2.91) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_wyckoff_ls_v1 | volatility | Conditional | 0.0870 | high | -0.0865 | 1117 | False |
| 2 | custom.tc_wyckoff_ls_v1 | dispersion | Mixed / Moderate | 0.0547 | normal | -0.0874 | 1177 | False |
| 3 | custom.tc_wyckoff_ls_v1 | trend | Mixed / Moderate | 0.0545 | bull | -0.0786 | 712 | False |
| 4 | custom.tc_wyckoff_ls_v1 | liquidity | Stable | 0.0538 | high | -0.0717 | 760 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_wyckoff_ls_v1 | dispersion | normal | -0.0874 | 0.0874 | invert | 1177 | 0.4622 |
| 2 | custom.tc_wyckoff_ls_v1 | volatility | high | -0.0865 | 0.0865 | invert | 1117 | 0.4503 |
| 3 | custom.tc_wyckoff_ls_v1 | trend | bull | -0.0786 | 0.0786 | invert | 712 | 0.4775 |
| 4 | custom.tc_wyckoff_ls_v1 | liquidity | high | -0.0717 | 0.0717 | invert | 760 | 0.4645 |
| 5 | custom.tc_wyckoff_ls_v1 | liquidity | normal | -0.0658 | 0.0658 | invert | 1454 | 0.4697 |
| 6 | custom.tc_wyckoff_ls_v1 | trend | neutral | -0.0561 | 0.0561 | invert | 1711 | 0.4752 |
| 7 | custom.tc_wyckoff_ls_v1 | volatility | low | -0.0533 | 0.0533 | invert | 1281 | 0.4887 |
| 8 | custom.tc_wyckoff_ls_v1 | dispersion | high | -0.0363 | 0.0363 | invert | 875 | 0.4857 |
| 9 | custom.tc_wyckoff_ls_v1 | dispersion | low | -0.0327 | 0.0327 | invert | 924 | 0.4805 |
| 10 | custom.tc_wyckoff_ls_v1 | trend | bear | -0.0242 | 0.0242 | invert | 553 | 0.4702 |
| 11 | custom.tc_wyckoff_ls_v1 | liquidity | starved | -0.0180 | 0.0180 | invert | 762 | 0.4948 |
| 12 | custom.tc_wyckoff_ls_v1 | volatility | normal | 0.0005 | 0.0005 | original | 578 | 0.4913 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
