# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1776**; upper quartile: **0.1904**.
- IR-spread upper quartile: **0.0637**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 970 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1547, t=5.15) | - | - |
| dispersion | normal | 1242 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1819, t=7.03) | - | - |
| dispersion | high | 943 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1895, t=6.43) | - | - |
| liquidity | starved | 804 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1884, t=6.23) | - | - |
| liquidity | normal | 1540 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1733, t=7.00) | - | - |
| liquidity | high | 812 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1694, t=5.20) | - | - |
| trend | bear | 569 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1931, t=4.66) | - | - |
| trend | neutral | 1818 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1497, t=6.30) | - | - |
| trend | bull | 769 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.2241, t=6.53) | - | - |
| volatility | low | 1282 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.2062, t=8.44) | - | - |
| volatility | normal | 599 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1639, t=4.34) | - | - |
| volatility | high | 1155 | False | 1/1 | `+custom.tc_surge_calm_v2_h3` (IR=0.1460, t=5.32) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_surge_calm_v2_h3 | trend | Conditional | 0.0744 | bull | 0.2241 | 769 | False |
| 2 | custom.tc_surge_calm_v2_h3 | volatility | Mixed / Moderate | 0.0602 | low | 0.2062 | 1282 | False |
| 3 | custom.tc_surge_calm_v2_h3 | dispersion | Mixed / Moderate | 0.0347 | high | 0.1895 | 943 | False |
| 4 | custom.tc_surge_calm_v2_h3 | liquidity | Mixed / Moderate | 0.0190 | starved | 0.1884 | 804 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_surge_calm_v2_h3 | trend | bull | 0.2241 | 0.2241 | original | 769 | 0.5800 |
| 2 | custom.tc_surge_calm_v2_h3 | volatility | low | 0.2062 | 0.2062 | original | 1282 | 0.5764 |
| 3 | custom.tc_surge_calm_v2_h3 | trend | bear | 0.1931 | 0.1931 | original | 569 | 0.5817 |
| 4 | custom.tc_surge_calm_v2_h3 | dispersion | high | 0.1895 | 0.1895 | original | 943 | 0.5748 |
| 5 | custom.tc_surge_calm_v2_h3 | liquidity | starved | 0.1884 | 0.1884 | original | 804 | 0.5609 |
| 6 | custom.tc_surge_calm_v2_h3 | dispersion | normal | 0.1819 | 0.1819 | original | 1242 | 0.5644 |
| 7 | custom.tc_surge_calm_v2_h3 | liquidity | normal | 0.1733 | 0.1733 | original | 1540 | 0.5643 |
| 8 | custom.tc_surge_calm_v2_h3 | liquidity | high | 0.1694 | 0.1694 | original | 812 | 0.5640 |
| 9 | custom.tc_surge_calm_v2_h3 | volatility | normal | 0.1639 | 0.1639 | original | 599 | 0.5676 |
| 10 | custom.tc_surge_calm_v2_h3 | dispersion | low | 0.1547 | 0.1547 | original | 970 | 0.5515 |
| 11 | custom.tc_surge_calm_v2_h3 | trend | neutral | 0.1497 | 0.1497 | original | 1818 | 0.5506 |
| 12 | custom.tc_surge_calm_v2_h3 | volatility | high | 0.1460 | 0.1460 | original | 1155 | 0.5455 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
