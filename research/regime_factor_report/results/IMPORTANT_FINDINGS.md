# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **1248**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **16**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0457**; upper quartile: **0.0714**.
- IR-spread upper quartile: **0.0513**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **8**
- Conditional: **37**
- Stable: **0**
- Mixed / Moderate: **24**
- Weak / Noise: **8**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **8**
- Conditional: **54**
- Stable: **32**
- Mixed / Moderate: **116**
- Weak / Noise: **98**
- Data Quality Issue: **4**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 4090 | False | 45/77 | `+worldquant.alpha040` (IR=0.1757, t=10.77) | `+worldquant.alpha094` (IR=0.1268, t=8.13) | `+worldquant.alpha044` (IR=0.1145, t=7.48) |
| dispersion | normal | 5192 | False | 44/77 | `+worldquant.alpha040` (IR=0.1471, t=10.39) | `+worldquant.alpha094` (IR=0.1337, t=9.94) | `+worldquant.alpha016` (IR=0.1049, t=7.79) |
| dispersion | high | 4095 | False | 26/77 | `+worldquant.alpha040` (IR=0.1244, t=7.93) | `+worldquant.alpha094` (IR=0.1098, t=7.20) | `+worldquant.alpha016` (IR=0.0966, t=6.57) |
| liquidity | starved | 3344 | False | 47/77 | `+worldquant.alpha040` (IR=0.2005, t=12.01) | `+worldquant.alpha094` (IR=0.1703, t=10.54) | `+worldquant.alpha073` (IR=0.1617, t=9.55) |
| liquidity | normal | 6485 | False | 45/77 | `+worldquant.alpha040` (IR=0.1636, t=12.60) | `+worldquant.alpha094` (IR=0.1358, t=10.69) | `+worldquant.alpha016` (IR=0.1206, t=9.73) |
| liquidity | high | 3548 | False | 13/77 | `+worldquant.alpha040` (IR=0.0810, t=4.54) | `+worldquant.alpha037` (IR=0.0803, t=4.64) | `+worldquant.alpha036` (IR=0.0762, t=4.19) |
| trend | bear | 5367 | False | 40/77 | `+worldquant.alpha040` (IR=0.1479, t=10.75) | `+worldquant.alpha094` (IR=0.1142, t=8.50) | `+worldquant.alpha044` (IR=0.1053, t=7.51) |
| trend | neutral | 7821 | False | 45/77 | `+worldquant.alpha040` (IR=0.1475, t=13.03) | `+worldquant.alpha094` (IR=0.1297, t=11.86) | `+worldquant.alpha016` (IR=0.1191, t=11.27) |
| trend | bull | 189 | True | 1/77 | `+worldquant.alpha040` (IR=0.2269, t=3.31) | - | - |
| volatility | low | 5143 | False | 34/77 | `+worldquant.alpha040` (IR=0.1638, t=11.80) | `+worldquant.alpha094` (IR=0.1354, t=9.20) | `+worldquant.alpha073` (IR=0.1192, t=8.33) |
| volatility | normal | 3491 | False | 38/77 | `+worldquant.alpha040` (IR=0.1512, t=8.90) | `+worldquant.alpha094` (IR=0.1103, t=7.21) | `+worldquant.alpha016` (IR=0.1095, t=6.96) |
| volatility | high | 4716 | False | 40/77 | `+worldquant.alpha040` (IR=0.1326, t=9.02) | `+worldquant.alpha094` (IR=0.1247, t=8.64) | `+worldquant.alpha036` (IR=0.1020, t=6.46) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha101 | trend | Regime-Reversal | 0.2468 | bull | 0.1866 | 189 | True |
| 2 | worldquant.alpha035 | trend | Regime-Reversal | 0.2264 | bull | -0.1500 | 189 | True |
| 3 | worldquant.alpha086 | trend | Regime-Reversal | 0.1869 | bull | -0.1591 | 189 | True |
| 4 | worldquant.alpha084 | trend | Regime-Reversal | 0.1671 | bear | 0.0853 | 5367 | False |
| 5 | worldquant.alpha013 | trend | Conditional | 0.1424 | bull | 0.1756 | 189 | True |
| 6 | worldquant.alpha065 | trend | Regime-Reversal | 0.1390 | bear | 0.0759 | 5365 | False |
| 7 | worldquant.alpha016 | trend | Conditional | 0.1356 | bull | 0.2185 | 189 | True |
| 8 | worldquant.alpha042 | trend | Conditional | 0.1310 | bull | 0.1358 | 186 | True |
| 9 | worldquant.alpha055 | trend | Conditional | 0.1239 | bull | 0.1929 | 189 | True |
| 10 | worldquant.alpha040 | liquidity | Conditional | 0.1195 | starved | 0.2005 | 3344 | False |
| 11 | worldquant.alpha023 | trend | Conditional | 0.1193 | bull | 0.1239 | 189 | True |
| 12 | worldquant.alpha077 | trend | Regime-Reversal | 0.1135 | bull | -0.0736 | 189 | True |
| 13 | worldquant.alpha003 | trend | Conditional | 0.1105 | bull | 0.1776 | 189 | True |
| 14 | worldquant.alpha029 | liquidity | Conditional | 0.1091 | starved | 0.1532 | 3344 | False |
| 15 | worldquant.alpha039 | trend | Conditional | 0.1089 | bull | 0.1429 | 189 | True |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha040 | liquidity | starved | 0.2005 | 0.2005 | original | 3344 | 0.5882 |
| 2 | worldquant.alpha040 | dispersion | low | 0.1757 | 0.1757 | original | 4090 | 0.5800 |
| 3 | worldquant.alpha094 | liquidity | starved | 0.1703 | 0.1703 | original | 3339 | 0.5855 |
| 4 | worldquant.alpha040 | volatility | low | 0.1638 | 0.1638 | original | 5143 | 0.5837 |
| 5 | worldquant.alpha040 | liquidity | normal | 0.1636 | 0.1636 | original | 6485 | 0.5801 |
| 6 | worldquant.alpha073 | liquidity | starved | 0.1617 | 0.1617 | original | 3344 | 0.5700 |
| 7 | worldquant.alpha029 | liquidity | starved | 0.1532 | 0.1532 | original | 3344 | 0.5727 |
| 8 | worldquant.alpha040 | volatility | normal | 0.1512 | 0.1512 | original | 3491 | 0.5729 |
| 9 | worldquant.alpha040 | trend | bear | 0.1479 | 0.1479 | original | 5367 | 0.5741 |
| 10 | worldquant.alpha040 | trend | neutral | 0.1475 | 0.1475 | original | 7821 | 0.5735 |
| 11 | worldquant.alpha040 | dispersion | normal | 0.1471 | 0.1471 | original | 5192 | 0.5794 |
| 12 | worldquant.alpha094 | liquidity | normal | 0.1358 | 0.1358 | original | 6474 | 0.5660 |
| 13 | worldquant.alpha094 | volatility | low | 0.1354 | 0.1354 | original | 5138 | 0.5708 |
| 14 | worldquant.alpha094 | dispersion | normal | 0.1337 | 0.1337 | original | 5175 | 0.5731 |
| 15 | worldquant.alpha040 | volatility | high | 0.1326 | 0.1326 | original | 4716 | 0.5655 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha040 | trend | bull | 0.2269 | 0.2269 | 189 | 0.0141 |
| 2 | worldquant.alpha016 | trend | bull | 0.2185 | 0.2185 | 189 | 0.0141 |
| 3 | worldquant.alpha094 | trend | bull | 0.1979 | 0.1979 | 189 | 0.0142 |
| 4 | worldquant.alpha055 | trend | bull | 0.1929 | 0.1929 | 189 | 0.0142 |
| 5 | worldquant.alpha101 | trend | bull | 0.1866 | 0.1866 | 189 | 0.0141 |
| 6 | worldquant.alpha073 | trend | bull | 0.1866 | 0.1866 | 189 | 0.0141 |
| 7 | worldquant.alpha036 | trend | bull | 0.1782 | 0.1782 | 189 | 0.0142 |
| 8 | worldquant.alpha003 | trend | bull | 0.1776 | 0.1776 | 189 | 0.0141 |
| 9 | worldquant.alpha013 | trend | bull | 0.1756 | 0.1756 | 189 | 0.0141 |
| 10 | worldquant.alpha029 | trend | bull | 0.1611 | 0.1611 | 189 | 0.0141 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
