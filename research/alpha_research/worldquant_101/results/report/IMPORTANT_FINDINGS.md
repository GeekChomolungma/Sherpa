# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **936**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **26**.
- Factors with missing/zero-sample rows: **worldquant.alpha042, worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0649**; upper quartile: **0.1007**.
- IR-spread upper quartile: **0.0679**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **6**
- Conditional: **23**
- Stable: **0**
- Mixed / Moderate: **31**
- Weak / Noise: **16**
- Data Quality Issue: **2**

## Dimension-level classification counts

- Regime-Reversal: **6**
- Conditional: **30**
- Stable: **34**
- Mixed / Moderate: **133**
- Weak / Noise: **101**
- Data Quality Issue: **8**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 1688 | False | 34/76 | `+worldquant.alpha040` (IR=0.2200, t=8.64) | `+worldquant.alpha044` (IR=0.1800, t=7.48) | `+worldquant.alpha094` (IR=0.1779, t=7.16) |
| dispersion | normal | 2046 | False | 35/76 | `+worldquant.alpha040` (IR=0.2206, t=10.51) | `+worldquant.alpha094` (IR=0.1834, t=8.61) | `+worldquant.alpha016` (IR=0.1535, t=7.21) |
| dispersion | high | 1611 | False | 39/76 | `+worldquant.alpha040` (IR=0.2224, t=9.22) | `+worldquant.alpha016` (IR=0.1910, t=7.81) | `+worldquant.alpha094` (IR=0.1739, t=7.45) |
| liquidity | starved | 1383 | False | 31/76 | `+worldquant.alpha040` (IR=0.2474, t=9.31) | `+worldquant.alpha094` (IR=0.2003, t=7.31) | `+worldquant.alpha044` (IR=0.1758, t=6.53) |
| liquidity | normal | 2584 | False | 44/76 | `+worldquant.alpha040` (IR=0.2281, t=11.82) | `+worldquant.alpha016` (IR=0.1872, t=9.80) | `+worldquant.alpha094` (IR=0.1854, t=9.96) |
| liquidity | high | 1378 | False | 23/76 | `+worldquant.alpha040` (IR=0.1830, t=6.66) | `+worldquant.alpha055` (IR=0.1565, t=5.65) | `+worldquant.alpha025` (IR=0.1561, t=5.79) |
| trend | bear | 1538 | False | 32/76 | `+worldquant.alpha040` (IR=0.2047, t=7.69) | `+worldquant.alpha044` (IR=0.1752, t=6.83) | `+worldquant.alpha016` (IR=0.1599, t=6.27) |
| trend | neutral | 3494 | False | 48/76 | `+worldquant.alpha040` (IR=0.2263, t=13.68) | `+worldquant.alpha094` (IR=0.1852, t=11.10) | `+worldquant.alpha016` (IR=0.1765, t=10.41) |
| trend | bull | 313 | True | 7/76 | `+worldquant.alpha040` (IR=0.2452, t=4.39) | `+worldquant.alpha094` (IR=0.2408, t=4.67) | `+worldquant.alpha036` (IR=0.1914, t=3.43) |
| volatility | low | 2180 | False | 37/76 | `+worldquant.alpha040` (IR=0.2417, t=11.99) | `+worldquant.alpha094` (IR=0.1746, t=8.43) | `+worldquant.alpha044` (IR=0.1544, t=7.65) |
| volatility | normal | 1197 | False | 35/76 | `+worldquant.alpha040` (IR=0.2229, t=7.61) | `+worldquant.alpha025` (IR=0.1934, t=6.66) | `+worldquant.alpha016` (IR=0.1688, t=6.06) |
| volatility | high | 1849 | False | 34/76 | `+worldquant.alpha040` (IR=0.2054, t=9.19) | `+worldquant.alpha016` (IR=0.1987, t=8.56) | `+worldquant.alpha094` (IR=0.1929, t=8.97) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha030 | trend | Regime-Reversal | 0.1771 | bull | -0.1086 | 313 | True |
| 2 | worldquant.alpha101 | trend | Regime-Reversal | 0.1616 | bear | -0.1142 | 1538 | False |
| 3 | worldquant.alpha023 | trend | Regime-Reversal | 0.1526 | bull | -0.1003 | 313 | True |
| 4 | worldquant.alpha020 | trend | Conditional | 0.1507 | bull | -0.1562 | 313 | True |
| 5 | worldquant.alpha035 | trend | Conditional | 0.1496 | bear | 0.1230 | 1538 | False |
| 6 | worldquant.alpha024 | trend | Regime-Reversal | 0.1389 | bear | 0.1053 | 1487 | False |
| 7 | worldquant.alpha054 | liquidity | Regime-Reversal | 0.1277 | starved | -0.0824 | 1383 | False |
| 8 | worldquant.alpha054 | trend | Conditional | 0.1256 | bull | -0.1195 | 313 | True |
| 9 | worldquant.alpha077 | trend | Conditional | 0.1215 | bull | 0.1703 | 313 | True |
| 10 | worldquant.alpha036 | trend | Conditional | 0.1176 | bull | 0.1914 | 313 | True |
| 11 | worldquant.alpha001 | trend | Mixed / Moderate | 0.1143 | neutral | -0.0925 | 3489 | False |
| 12 | worldquant.alpha045 | dispersion | Mixed / Moderate | 0.1128 | high | 0.0853 | 1611 | False |
| 13 | worldquant.alpha043 | liquidity | Regime-Reversal | 0.1119 | normal | 0.0763 | 2584 | False |
| 14 | worldquant.alpha062 | trend | Weak / Noise | 0.1111 | bear | 0.0632 | 1538 | False |
| 15 | worldquant.alpha031 | dispersion | Conditional | 0.1103 | high | 0.1251 | 1611 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha040 | liquidity | starved | 0.2474 | 0.2474 | original | 1383 | 0.5879 |
| 2 | worldquant.alpha040 | volatility | low | 0.2417 | 0.2417 | original | 2180 | 0.5991 |
| 3 | worldquant.alpha040 | liquidity | normal | 0.2281 | 0.2281 | original | 2584 | 0.5937 |
| 4 | worldquant.alpha040 | trend | neutral | 0.2263 | 0.2263 | original | 3494 | 0.5867 |
| 5 | worldquant.alpha040 | volatility | normal | 0.2229 | 0.2229 | original | 1197 | 0.5764 |
| 6 | worldquant.alpha040 | dispersion | high | 0.2224 | 0.2224 | original | 1611 | 0.5847 |
| 7 | worldquant.alpha040 | dispersion | normal | 0.2206 | 0.2206 | original | 2046 | 0.5894 |
| 8 | worldquant.alpha040 | dispersion | low | 0.2200 | 0.2200 | original | 1688 | 0.5794 |
| 9 | worldquant.alpha040 | volatility | high | 0.2054 | 0.2054 | original | 1849 | 0.5765 |
| 10 | worldquant.alpha040 | trend | bear | 0.2047 | 0.2047 | original | 1538 | 0.5767 |
| 11 | worldquant.alpha094 | liquidity | starved | 0.2003 | 0.2003 | original | 1383 | 0.5770 |
| 12 | worldquant.alpha016 | volatility | high | 0.1987 | 0.1987 | original | 1849 | 0.5895 |
| 13 | worldquant.alpha025 | volatility | normal | 0.1934 | 0.1934 | original | 1197 | 0.5856 |
| 14 | worldquant.alpha094 | volatility | high | 0.1929 | 0.1929 | original | 1849 | 0.5700 |
| 15 | worldquant.alpha016 | dispersion | high | 0.1910 | 0.1910 | original | 1611 | 0.5810 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha040 | trend | bull | 0.2452 | 0.2452 | 313 | 0.0586 |
| 2 | worldquant.alpha094 | trend | bull | 0.2408 | 0.2408 | 313 | 0.0586 |
| 3 | worldquant.alpha036 | trend | bull | 0.1914 | 0.1914 | 313 | 0.0594 |
| 4 | worldquant.alpha044 | trend | bull | 0.1793 | 0.1793 | 313 | 0.0586 |
| 5 | worldquant.alpha016 | trend | bull | 0.1721 | 0.1721 | 313 | 0.0586 |
| 6 | worldquant.alpha077 | trend | bull | 0.1703 | 0.1703 | 313 | 0.0586 |
| 7 | worldquant.alpha065 | trend | bull | 0.1659 | 0.1659 | 313 | 0.0586 |
| 8 | worldquant.alpha019 | trend | bull | 0.1609 | 0.1609 | 313 | 0.0600 |
| 9 | worldquant.alpha020 | trend | bull | -0.1562 | 0.1562 | 313 | 0.0586 |
| 10 | worldquant.alpha039 | trend | bull | 0.1554 | 0.1554 | 313 | 0.0600 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
