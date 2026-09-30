# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **9**; factors: **3**; dimensions: **1**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1075**; upper quartile: **0.1249**.
- IR-spread upper quartile: **0.0945**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **0**
- Conditional: **1**
- Stable: **0**
- Mixed / Moderate: **1**
- Weak / Noise: **1**
- Data Quality Issue: **0**

## Dimension-level classification counts

- Regime-Reversal: **0**
- Conditional: **1**
- Stable: **0**
- Mixed / Moderate: **1**
- Weak / Noise: **1**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| trend | bear | 1151 | False | 2/3 | `-custom.close_momentum_20` (IR=-0.1249, t=-4.31) | `-custom.liquid_momentum_rank` (IR=-0.1075, t=-3.57) | - |
| trend | neutral | 3050 | False | 2/3 | `-custom.close_momentum_20` (IR=-0.1137, t=-6.30) | `-custom.liquid_momentum_rank` (IR=-0.1060, t=-5.86) | - |
| trend | bull | 1144 | False | 2/3 | `-custom.liquid_momentum_rank` (IR=-0.2161, t=-7.29) | `-custom.close_momentum_20` (IR=-0.1926, t=-6.55) | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.liquid_momentum_rank | trend | Conditional | 0.1101 | bull | -0.2161 | 1144 | False |
| 2 | custom.close_momentum_20 | trend | Mixed / Moderate | 0.0789 | bull | -0.1926 | 1144 | False |
| 3 | custom.volume_surge | trend | Weak / Noise | 0.0263 | bear | 0.0200 | 1151 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.liquid_momentum_rank | trend | bull | -0.2161 | 0.2161 | invert | 1144 | 0.4012 |
| 2 | custom.close_momentum_20 | trend | bull | -0.1926 | 0.1926 | invert | 1144 | 0.4196 |
| 3 | custom.close_momentum_20 | trend | bear | -0.1249 | 0.1249 | invert | 1151 | 0.4405 |
| 4 | custom.close_momentum_20 | trend | neutral | -0.1137 | 0.1137 | invert | 3050 | 0.4459 |
| 5 | custom.liquid_momentum_rank | trend | bear | -0.1075 | 0.1075 | invert | 1151 | 0.4414 |
| 6 | custom.liquid_momentum_rank | trend | neutral | -0.1060 | 0.1060 | invert | 3050 | 0.4554 |
| 7 | custom.volume_surge | trend | bear | 0.0200 | 0.0200 | original | 1151 | 0.5222 |
| 8 | custom.volume_surge | trend | neutral | -0.0062 | 0.0062 | invert | 3050 | 0.5020 |
| 9 | custom.volume_surge | trend | bull | 0.0010 | 0.0010 | original | 1144 | 0.4878 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
