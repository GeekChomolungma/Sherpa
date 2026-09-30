# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **6**; factors: **2**; dimensions: **1**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0931**; upper quartile: **0.1330**.
- IR-spread upper quartile: **0.0534**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **0**
- Conditional: **0**
- Stable: **1**
- Mixed / Moderate: **0**
- Weak / Noise: **1**
- Data Quality Issue: **0**

## Dimension-level classification counts

- Regime-Reversal: **0**
- Conditional: **0**
- Stable: **1**
- Mixed / Moderate: **0**
- Weak / Noise: **1**
- Data Quality Issue: **0**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| trend | bear | 1538 | False | 1/2 | `-custom.close_momentum_20` (IR=-0.1282, t=-5.23) | - | - |
| trend | neutral | 3494 | False | 1/2 | `-custom.close_momentum_20` (IR=-0.1345, t=-7.94) | - | - |
| trend | bull | 313 | True | 0/2 | - | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.volume_surge | trend | Weak / Noise | 0.0670 | bull | 0.0579 | 313 | True |
| 2 | custom.close_momentum_20 | trend | Stable | 0.0126 | bull | -0.1408 | 313 | True |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.close_momentum_20 | trend | neutral | -0.1345 | 0.1345 | invert | 3494 | 0.4405 |
| 2 | custom.close_momentum_20 | trend | bear | -0.1282 | 0.1282 | invert | 1538 | 0.4350 |
| 3 | custom.volume_surge | trend | bear | -0.0091 | 0.0091 | invert | 1538 | 0.5091 |
| 4 | custom.volume_surge | trend | neutral | 0.0001 | 0.0001 | original | 3494 | 0.4994 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | custom.close_momentum_20 | trend | bull | -0.1408 | 0.1408 | 313 | 0.0586 |
| 2 | custom.volume_surge | trend | bull | 0.0579 | 0.0579 | 313 | 0.0586 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
