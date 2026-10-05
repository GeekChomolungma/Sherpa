# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **9**; factors: **3**; dimensions: **1**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1149**; upper quartile: **0.1815**.
- IR-spread upper quartile: **0.0809**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **0**
- Conditional: **1**
- Stable: **1**
- Mixed / Moderate: **0**
- Weak / Noise: **1**
- Data Quality Issue: **0**

## Dimension-level classification counts

- Regime-Reversal: **0**
- Conditional: **1**
- Stable: **1**
- Mixed / Moderate: **0**
- Weak / Noise: **1**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| trend | bear | 569 | False | 2/3 | `-custom.liquid_momentum_rank` (IR=-0.2045, t=-4.64) | `-custom.close_momentum_20` (IR=-0.1815, t=-4.25) | - |
| trend | neutral | 1818 | False | 2/3 | `-custom.close_momentum_20` (IR=-0.1149, t=-4.91) | `-custom.liquid_momentum_rank` (IR=-0.1106, t=-4.86) | - |
| trend | bull | 768 | False | 2/3 | `-custom.liquid_momentum_rank` (IR=-0.2048, t=-5.70) | `-custom.close_momentum_20` (IR=-0.1711, t=-4.64) | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.liquid_momentum_rank | trend | Conditional | 0.0942 | bull | -0.2048 | 768 | False |
| 2 | custom.volume_surge | trend | Weak / Noise | 0.0676 | bull | 0.0345 | 768 | False |
| 3 | custom.close_momentum_20 | trend | Stable | 0.0666 | bear | -0.1815 | 569 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.liquid_momentum_rank | trend | bull | -0.2048 | 0.2048 | invert | 768 | 0.4036 |
| 2 | custom.liquid_momentum_rank | trend | bear | -0.2045 | 0.2045 | invert | 569 | 0.3937 |
| 3 | custom.close_momentum_20 | trend | bear | -0.1815 | 0.1815 | invert | 569 | 0.4218 |
| 4 | custom.close_momentum_20 | trend | bull | -0.1711 | 0.1711 | invert | 768 | 0.4284 |
| 5 | custom.close_momentum_20 | trend | neutral | -0.1149 | 0.1149 | invert | 1818 | 0.4521 |
| 6 | custom.liquid_momentum_rank | trend | neutral | -0.1106 | 0.1106 | invert | 1818 | 0.4664 |
| 7 | custom.volume_surge | trend | bull | 0.0345 | 0.0345 | original | 768 | 0.5039 |
| 8 | custom.volume_surge | trend | bear | -0.0330 | 0.0330 | invert | 569 | 0.5062 |
| 9 | custom.volume_surge | trend | neutral | 0.0053 | 0.0053 | original | 1818 | 0.5006 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
