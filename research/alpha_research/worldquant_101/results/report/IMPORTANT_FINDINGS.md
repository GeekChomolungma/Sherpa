# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **936**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **26**.
- Factors with missing/zero-sample rows: **worldquant.alpha042, worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0615**; upper quartile: **0.1023**.
- IR-spread upper quartile: **0.0825**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **6**
- Conditional: **31**
- Stable: **0**
- Mixed / Moderate: **29**
- Weak / Noise: **10**
- Data Quality Issue: **2**

## Dimension-level classification counts

- Regime-Reversal: **7**
- Conditional: **46**
- Stable: **37**
- Mixed / Moderate: **137**
- Weak / Noise: **77**
- Data Quality Issue: **8**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 970 | False | 26/76 | `+worldquant.alpha040` (IR=0.2530, t=7.95) | `+worldquant.alpha016` (IR=0.2457, t=7.33) | `+worldquant.alpha094` (IR=0.2311, t=6.80) |
| dispersion | normal | 1242 | False | 24/76 | `+worldquant.alpha040` (IR=0.2111, t=7.62) | `+worldquant.alpha094` (IR=0.2046, t=7.16) | `+worldquant.alpha016` (IR=0.1792, t=6.18) |
| dispersion | high | 943 | False | 16/76 | `+worldquant.alpha040` (IR=0.2166, t=6.78) | `+worldquant.alpha016` (IR=0.2003, t=6.22) | `+worldquant.alpha036` (IR=0.1834, t=5.20) |
| liquidity | starved | 804 | False | 21/76 | `+worldquant.alpha094` (IR=0.2408, t=6.96) | `+worldquant.alpha016` (IR=0.2407, t=6.27) | `+worldquant.alpha040` (IR=0.2295, t=6.80) |
| liquidity | normal | 1540 | False | 32/76 | `+worldquant.alpha040` (IR=0.2393, t=10.07) | `+worldquant.alpha016` (IR=0.2028, t=7.95) | `+worldquant.alpha094` (IR=0.2019, t=8.10) |
| liquidity | high | 811 | False | 15/76 | `+worldquant.alpha040` (IR=0.1941, t=5.54) | `+worldquant.alpha036` (IR=0.1852, t=5.20) | `+worldquant.alpha016` (IR=0.1769, t=5.42) |
| trend | bear | 569 | False | 16/76 | `+worldquant.alpha016` (IR=0.2501, t=5.94) | `+worldquant.alpha094` (IR=0.2206, t=5.34) | `+worldquant.alpha040` (IR=0.2151, t=4.79) |
| trend | neutral | 1818 | False | 37/76 | `+worldquant.alpha040` (IR=0.2139, t=8.83) | `+worldquant.alpha016` (IR=0.1994, t=8.50) | `+worldquant.alpha044` (IR=0.1781, t=7.67) |
| trend | bull | 768 | False | 18/76 | `+worldquant.alpha040` (IR=0.2594, t=7.42) | `+worldquant.alpha094` (IR=0.2312, t=6.75) | `+worldquant.alpha016` (IR=0.1885, t=5.66) |
| volatility | low | 1282 | False | 26/76 | `+worldquant.alpha040` (IR=0.2575, t=9.85) | `+worldquant.alpha094` (IR=0.2136, t=7.79) | `+worldquant.alpha016` (IR=0.1954, t=7.57) |
| volatility | normal | 599 | False | 16/76 | `+worldquant.alpha025` (IR=0.2271, t=5.46) | `+worldquant.alpha016` (IR=0.2210, t=5.63) | `+worldquant.alpha040` (IR=0.2146, t=5.73) |
| volatility | high | 1155 | False | 20/76 | `+worldquant.alpha016` (IR=0.2043, t=6.71) | `+worldquant.alpha036` (IR=0.1875, t=6.09) | `+worldquant.alpha040` (IR=0.1838, t=6.47) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha035 | trend | Conditional | 0.2163 | bear | 0.1987 | 569 | False |
| 2 | worldquant.alpha061 | dispersion | Conditional | 0.1827 | low | 0.1779 | 953 | False |
| 3 | worldquant.alpha061 | liquidity | Conditional | 0.1706 | starved | 0.1578 | 793 | False |
| 4 | worldquant.alpha025 | volatility | Conditional | 0.1677 | normal | 0.2271 | 599 | False |
| 5 | worldquant.alpha081 | liquidity | Conditional | 0.1676 | starved | 0.1661 | 804 | False |
| 6 | worldquant.alpha066 | trend | Conditional | 0.1568 | bear | 0.1878 | 569 | False |
| 7 | worldquant.alpha073 | liquidity | Conditional | 0.1563 | starved | 0.1973 | 804 | False |
| 8 | worldquant.alpha054 | trend | Conditional | 0.1538 | bull | -0.1297 | 768 | False |
| 9 | worldquant.alpha025 | trend | Conditional | 0.1538 | bull | 0.1709 | 768 | False |
| 10 | worldquant.alpha020 | liquidity | Conditional | 0.1527 | high | -0.1512 | 811 | False |
| 11 | worldquant.alpha101 | trend | Conditional | 0.1525 | bear | -0.1427 | 569 | False |
| 12 | worldquant.alpha006 | trend | Conditional | 0.1403 | bear | 0.1739 | 569 | False |
| 13 | worldquant.alpha083 | trend | Conditional | 0.1341 | bull | 0.1249 | 768 | False |
| 14 | worldquant.alpha099 | trend | Regime-Reversal | 0.1325 | bear | 0.0922 | 569 | False |
| 15 | worldquant.alpha074 | liquidity | Conditional | 0.1324 | starved | 0.1408 | 804 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha040 | trend | bull | 0.2594 | 0.2594 | original | 768 | 0.6029 |
| 2 | worldquant.alpha040 | volatility | low | 0.2575 | 0.2575 | original | 1282 | 0.6076 |
| 3 | worldquant.alpha040 | dispersion | low | 0.2530 | 0.2530 | original | 970 | 0.5990 |
| 4 | worldquant.alpha016 | trend | bear | 0.2501 | 0.2501 | original | 569 | 0.5923 |
| 5 | worldquant.alpha016 | dispersion | low | 0.2457 | 0.2457 | original | 970 | 0.6031 |
| 6 | worldquant.alpha094 | liquidity | starved | 0.2408 | 0.2408 | original | 804 | 0.5908 |
| 7 | worldquant.alpha016 | liquidity | starved | 0.2407 | 0.2407 | original | 804 | 0.6032 |
| 8 | worldquant.alpha040 | liquidity | normal | 0.2393 | 0.2393 | original | 1540 | 0.5955 |
| 9 | worldquant.alpha094 | trend | bull | 0.2312 | 0.2312 | original | 768 | 0.5846 |
| 10 | worldquant.alpha094 | dispersion | low | 0.2311 | 0.2311 | original | 970 | 0.5825 |
| 11 | worldquant.alpha040 | liquidity | starved | 0.2295 | 0.2295 | original | 804 | 0.5933 |
| 12 | worldquant.alpha025 | volatility | normal | 0.2271 | 0.2271 | original | 599 | 0.5977 |
| 13 | worldquant.alpha016 | volatility | normal | 0.2210 | 0.2210 | original | 599 | 0.5943 |
| 14 | worldquant.alpha094 | trend | bear | 0.2206 | 0.2206 | original | 569 | 0.5870 |
| 15 | worldquant.alpha040 | dispersion | high | 0.2166 | 0.2166 | original | 943 | 0.5790 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
