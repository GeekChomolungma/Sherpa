# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **12**; factors: **1**; dimensions: **4**.
- Missing/zero-sample metric rows: **0**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1468**; upper quartile: **0.1599**.
- IR-spread upper quartile: **0.0662**. This is used as the primary 'regime-sensitive' cutoff.
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
| dispersion | low | 970 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1349, t=4.12) | - | - |
| dispersion | normal | 1236 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1890, t=6.62) | - | - |
| dispersion | high | 932 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1047, t=3.20) | - | - |
| liquidity | starved | 804 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1696, t=4.93) | - | - |
| liquidity | normal | 1531 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1461, t=5.56) | - | - |
| liquidity | high | 803 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1272, t=3.81) | - | - |
| trend | bear | 569 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1475, t=3.38) | - | - |
| trend | neutral | 1809 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1289, t=5.41) | - | - |
| trend | bull | 760 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1891, t=4.97) | - | - |
| volatility | low | 1282 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1556, t=5.11) | - | - |
| volatility | normal | 599 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1081, t=2.64) | - | - |
| volatility | high | 1155 | False | 1/1 | `+custom.tc_wyckoff_absorb_v1` (IR=0.1567, t=5.33) | - | - |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | custom.tc_wyckoff_absorb_v1 | dispersion | Conditional | 0.0843 | normal | 0.1890 | 1236 | False |
| 2 | custom.tc_wyckoff_absorb_v1 | trend | Mixed / Moderate | 0.0602 | bull | 0.1891 | 760 | False |
| 3 | custom.tc_wyckoff_absorb_v1 | volatility | Mixed / Moderate | 0.0486 | high | 0.1567 | 1155 | False |
| 4 | custom.tc_wyckoff_absorb_v1 | liquidity | Mixed / Moderate | 0.0423 | starved | 0.1696 | 804 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | custom.tc_wyckoff_absorb_v1 | trend | bull | 0.1891 | 0.1891 | original | 760 | 0.5776 |
| 2 | custom.tc_wyckoff_absorb_v1 | dispersion | normal | 0.1890 | 0.1890 | original | 1236 | 0.5809 |
| 3 | custom.tc_wyckoff_absorb_v1 | liquidity | starved | 0.1696 | 0.1696 | original | 804 | 0.5609 |
| 4 | custom.tc_wyckoff_absorb_v1 | volatility | high | 0.1567 | 0.1567 | original | 1155 | 0.5463 |
| 5 | custom.tc_wyckoff_absorb_v1 | volatility | low | 0.1556 | 0.1556 | original | 1282 | 0.5702 |
| 6 | custom.tc_wyckoff_absorb_v1 | trend | bear | 0.1475 | 0.1475 | original | 569 | 0.5589 |
| 7 | custom.tc_wyckoff_absorb_v1 | liquidity | normal | 0.1461 | 0.1461 | original | 1531 | 0.5624 |
| 8 | custom.tc_wyckoff_absorb_v1 | dispersion | low | 0.1349 | 0.1349 | original | 970 | 0.5454 |
| 9 | custom.tc_wyckoff_absorb_v1 | trend | neutral | 0.1289 | 0.1289 | original | 1809 | 0.5506 |
| 10 | custom.tc_wyckoff_absorb_v1 | liquidity | high | 0.1272 | 0.1272 | original | 803 | 0.5492 |
| 11 | custom.tc_wyckoff_absorb_v1 | volatility | normal | 0.1081 | 0.1081 | original | 599 | 0.5509 |
| 12 | custom.tc_wyckoff_absorb_v1 | dispersion | high | 0.1047 | 0.1047 | original | 932 | 0.5429 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
