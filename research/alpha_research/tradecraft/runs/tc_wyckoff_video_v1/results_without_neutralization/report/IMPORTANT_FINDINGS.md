# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1000**; upper quartile: **0.1192**.
- IR-spread upper quartile: **0.0704**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 924 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.0840, t=-2.48) | - | - |
| dispersion | normal | 1177 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.1454, t=-4.62) | - | - |
| dispersion | high | 875 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.0769, t=-2.20) | - | - |
| liquidity | starved | 762 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.0821, t=-2.35) | - | - |
| liquidity | normal | 1454 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.1172, t=-4.33) | - | - |
| liquidity | high | 760 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.1075, t=-3.27) | - | - |
| trend | bear | 553 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.0762, t=-1.74) | - | - |
| trend | neutral | 1711 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.0968, t=-3.71) | - | - |
| trend | bull | 712 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.1525, t=-3.98) | - | - |
| volatility | low | 1281 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.1032, t=-3.44) | - | - |
| volatility | normal | 578 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.0747, t=-1.81) | - | - |
| volatility | high | 1117 | False | 1/1 | `-custom.tc_wyckoff_video_v1` (IR=-0.1252, t=-4.27) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_wyckoff_video_v1 | trend | Conditional | 0.0763 | bull | -0.1525 | 712 | False |
| 2 | custom.tc_wyckoff_video_v1 | dispersion | Mixed / Moderate | 0.0684 | normal | -0.1454 | 1177 | False |
| 3 | custom.tc_wyckoff_video_v1 | volatility | Mixed / Moderate | 0.0505 | high | -0.1252 | 1117 | False |
| 4 | custom.tc_wyckoff_video_v1 | liquidity | Stable | 0.0351 | normal | -0.1172 | 1454 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_wyckoff_video_v1 | trend | bull | -0.1525 | 0.1525 | invert | 712 | 0.4480 |
| 2 | custom.tc_wyckoff_video_v1 | dispersion | normal | -0.1454 | 0.1454 | invert | 1177 | 0.4494 |
| 3 | custom.tc_wyckoff_video_v1 | volatility | high | -0.1252 | 0.1252 | invert | 1117 | 0.4387 |
| 4 | custom.tc_wyckoff_video_v1 | liquidity | normal | -0.1172 | 0.1172 | invert | 1454 | 0.4519 |
| 5 | custom.tc_wyckoff_video_v1 | liquidity | high | -0.1075 | 0.1075 | invert | 760 | 0.4579 |
| 6 | custom.tc_wyckoff_video_v1 | volatility | low | -0.1032 | 0.1032 | invert | 1281 | 0.4637 |
| 7 | custom.tc_wyckoff_video_v1 | trend | neutral | -0.0968 | 0.0968 | invert | 1711 | 0.4600 |
| 8 | custom.tc_wyckoff_video_v1 | dispersion | low | -0.0840 | 0.0840 | invert | 924 | 0.4513 |
| 9 | custom.tc_wyckoff_video_v1 | liquidity | starved | -0.0821 | 0.0821 | invert | 762 | 0.4567 |
| 10 | custom.tc_wyckoff_video_v1 | dispersion | high | -0.0769 | 0.0769 | invert | 875 | 0.4651 |
| 11 | custom.tc_wyckoff_video_v1 | trend | bear | -0.0762 | 0.0762 | invert | 553 | 0.4467 |
| 12 | custom.tc_wyckoff_video_v1 | volatility | normal | -0.0747 | 0.0747 | invert | 578 | 0.4654 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
