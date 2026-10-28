# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1580**; upper quartile: **0.1750**.
- IR-spread upper quartile: **0.0858**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 668 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1785, t=4.47) | - | - |
| dispersion | normal | 889 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1697, t=5.14) | - | - |
| dispersion | high | 702 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1186, t=3.35) | - | - |
| liquidity | starved | 510 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.2177, t=5.83) | - | - |
| liquidity | normal | 1112 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1519, t=5.35) | - | - |
| liquidity | high | 638 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1198, t=3.16) | - | - |
| trend | bear | 398 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.2098, t=4.40) | - | - |
| trend | neutral | 1272 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1369, t=4.69) | - | - |
| trend | bull | 590 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1638, t=4.56) | - | - |
| volatility | low | 872 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1738, t=5.48) | - | - |
| volatility | normal | 396 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.0920, t=2.24) | - | - |
| volatility | high | 872 | False | 1/1 | `+custom.tc_surge_calm_gated_v1` (IR=0.1523, t=4.56) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_surge_calm_gated_v1 | liquidity | Conditional | 0.0980 | starved | 0.2177 | 510 | False |
| 2 | custom.tc_surge_calm_gated_v1 | volatility | Mixed / Moderate | 0.0818 | low | 0.1738 | 872 | False |
| 3 | custom.tc_surge_calm_gated_v1 | trend | Mixed / Moderate | 0.0729 | bear | 0.2098 | 398 | False |
| 4 | custom.tc_surge_calm_gated_v1 | dispersion | Stable | 0.0599 | low | 0.1785 | 668 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_surge_calm_gated_v1 | liquidity | starved | 0.2177 | 0.2177 | original | 510 | 0.6118 |
| 2 | custom.tc_surge_calm_gated_v1 | trend | bear | 0.2098 | 0.2098 | original | 398 | 0.5879 |
| 3 | custom.tc_surge_calm_gated_v1 | dispersion | low | 0.1785 | 0.1785 | original | 668 | 0.5734 |
| 4 | custom.tc_surge_calm_gated_v1 | volatility | low | 0.1738 | 0.1738 | original | 872 | 0.5596 |
| 5 | custom.tc_surge_calm_gated_v1 | dispersion | normal | 0.1697 | 0.1697 | original | 889 | 0.5613 |
| 6 | custom.tc_surge_calm_gated_v1 | trend | bull | 0.1638 | 0.1638 | original | 590 | 0.5610 |
| 7 | custom.tc_surge_calm_gated_v1 | volatility | high | 0.1523 | 0.1523 | original | 872 | 0.5642 |
| 8 | custom.tc_surge_calm_gated_v1 | liquidity | normal | 0.1519 | 0.1519 | original | 1112 | 0.5486 |
| 9 | custom.tc_surge_calm_gated_v1 | trend | neutral | 0.1369 | 0.1369 | original | 1272 | 0.5519 |
| 10 | custom.tc_surge_calm_gated_v1 | liquidity | high | 0.1198 | 0.1198 | original | 638 | 0.5408 |
| 11 | custom.tc_surge_calm_gated_v1 | dispersion | high | 0.1186 | 0.1186 | original | 702 | 0.5484 |
| 12 | custom.tc_surge_calm_gated_v1 | volatility | normal | 0.0920 | 0.0920 | original | 396 | 0.5404 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
