# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1465**; upper quartile: **0.1771**.
- IR-spread upper quartile: **0.0946**. This is used as the primary 'regime-sensitive' cutoff.
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

Only alphas with |t_stat| >= 0 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 970 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1408, t=4.25) | - | - |
| dispersion | normal | 1242 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1734, t=6.04) | - | - |
| dispersion | high | 943 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1462, t=4.64) | - | - |
| liquidity | starved | 804 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.2010, t=6.61) | - | - |
| liquidity | normal | 1540 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1610, t=6.42) | - | - |
| liquidity | high | 812 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1032, t=3.12) | - | - |
| trend | bear | 569 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.2025, t=4.78) | - | - |
| trend | neutral | 1818 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1468, t=5.84) | - | - |
| trend | bull | 769 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1403, t=4.29) | - | - |
| volatility | low | 1282 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1884, t=7.17) | - | - |
| volatility | normal | 599 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.0949, t=2.54) | - | - |
| volatility | high | 1155 | False | 1/1 | `+custom.tc_surge_calm_v1` (IR=0.1393, t=4.65) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_surge_calm_v1 | liquidity | Conditional | 0.0979 | starved | 0.2010 | 804 | False |
| 2 | custom.tc_surge_calm_v1 | volatility | Mixed / Moderate | 0.0935 | low | 0.1884 | 1282 | False |
| 3 | custom.tc_surge_calm_v1 | trend | Mixed / Moderate | 0.0622 | bear | 0.2025 | 569 | False |
| 4 | custom.tc_surge_calm_v1 | dispersion | Mixed / Moderate | 0.0326 | normal | 0.1734 | 1242 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_surge_calm_v1 | trend | bear | 0.2025 | 0.2025 | original | 569 | 0.5747 |
| 2 | custom.tc_surge_calm_v1 | liquidity | starved | 0.2010 | 0.2010 | original | 804 | 0.5970 |
| 3 | custom.tc_surge_calm_v1 | volatility | low | 0.1884 | 0.1884 | original | 1282 | 0.5710 |
| 4 | custom.tc_surge_calm_v1 | dispersion | normal | 0.1734 | 0.1734 | original | 1242 | 0.5612 |
| 5 | custom.tc_surge_calm_v1 | liquidity | normal | 0.1610 | 0.1610 | original | 1540 | 0.5545 |
| 6 | custom.tc_surge_calm_v1 | trend | neutral | 0.1468 | 0.1468 | original | 1818 | 0.5578 |
| 7 | custom.tc_surge_calm_v1 | dispersion | high | 0.1462 | 0.1462 | original | 943 | 0.5610 |
| 8 | custom.tc_surge_calm_v1 | dispersion | low | 0.1408 | 0.1408 | original | 970 | 0.5588 |
| 9 | custom.tc_surge_calm_v1 | trend | bull | 0.1403 | 0.1403 | original | 769 | 0.5553 |
| 10 | custom.tc_surge_calm_v1 | volatility | high | 0.1393 | 0.1393 | original | 1155 | 0.5558 |
| 11 | custom.tc_surge_calm_v1 | liquidity | high | 0.1032 | 0.1032 | original | 812 | 0.5345 |
| 12 | custom.tc_surge_calm_v1 | volatility | normal | 0.0949 | 0.0949 | original | 599 | 0.5359 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
