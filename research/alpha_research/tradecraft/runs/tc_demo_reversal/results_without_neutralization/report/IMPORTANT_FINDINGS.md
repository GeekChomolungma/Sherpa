# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1276**; upper quartile: **0.1390**.
- IR-spread upper quartile: **0.0805**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 970 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1544, t=4.79) | - | - |
| dispersion | normal | 1242 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.0875, t=2.91) | - | - |
| dispersion | high | 943 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1327, t=4.30) | - | - |
| liquidity | starved | 804 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1670, t=4.89) | - | - |
| liquidity | normal | 1540 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1225, t=4.79) | - | - |
| liquidity | high | 812 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.0761, t=2.20) | - | - |
| trend | bear | 569 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1756, t=3.90) | - | - |
| trend | neutral | 1818 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.0985, t=4.48) | - | - |
| trend | bull | 769 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1327, t=3.55) | - | - |
| volatility | low | 1282 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1339, t=4.86) | - | - |
| volatility | normal | 599 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.0955, t=2.46) | - | - |
| volatility | high | 1155 | False | 1/1 | `+custom.tc_demo_reversal` (IR=0.1045, t=3.53) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_demo_reversal | liquidity | Conditional | 0.0909 | starved | 0.1670 | 804 | False |
| 2 | custom.tc_demo_reversal | trend | Mixed / Moderate | 0.0771 | bear | 0.1756 | 569 | False |
| 3 | custom.tc_demo_reversal | dispersion | Mixed / Moderate | 0.0669 | low | 0.1544 | 970 | False |
| 4 | custom.tc_demo_reversal | volatility | Mixed / Moderate | 0.0384 | low | 0.1339 | 1282 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_demo_reversal | trend | bear | 0.1756 | 0.1756 | original | 569 | 0.5852 |
| 2 | custom.tc_demo_reversal | liquidity | starved | 0.1670 | 0.1670 | original | 804 | 0.5697 |
| 3 | custom.tc_demo_reversal | dispersion | low | 0.1544 | 0.1544 | original | 970 | 0.5701 |
| 4 | custom.tc_demo_reversal | volatility | low | 0.1339 | 0.1339 | original | 1282 | 0.5710 |
| 5 | custom.tc_demo_reversal | trend | bull | 0.1327 | 0.1327 | original | 769 | 0.5657 |
| 6 | custom.tc_demo_reversal | dispersion | high | 0.1327 | 0.1327 | original | 943 | 0.5631 |
| 7 | custom.tc_demo_reversal | liquidity | normal | 0.1225 | 0.1225 | original | 1540 | 0.5610 |
| 8 | custom.tc_demo_reversal | volatility | high | 0.1045 | 0.1045 | original | 1155 | 0.5455 |
| 9 | custom.tc_demo_reversal | trend | neutral | 0.0985 | 0.0985 | original | 1818 | 0.5429 |
| 10 | custom.tc_demo_reversal | volatility | normal | 0.0955 | 0.0955 | original | 599 | 0.5309 |
| 11 | custom.tc_demo_reversal | dispersion | normal | 0.0875 | 0.0875 | original | 1242 | 0.5403 |
| 12 | custom.tc_demo_reversal | liquidity | high | 0.0761 | 0.0761 | original | 812 | 0.5333 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
