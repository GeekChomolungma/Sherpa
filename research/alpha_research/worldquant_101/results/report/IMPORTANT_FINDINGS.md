# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **936**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **26**.
- Factors with missing/zero-sample rows: **worldquant.alpha042, worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0655**; upper quartile: **0.1005**.
- IR-spread upper quartile: **0.0608**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **2**
- Conditional: **26**
- Stable: **0**
- Mixed / Moderate: **31**
- Weak / Noise: **17**
- Data Quality Issue: **2**

## Dimension-level classification counts

- Regime-Reversal: **2**
- Conditional: **39**
- Stable: **32**
- Mixed / Moderate: **129**
- Weak / Noise: **102**
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
| trend | bear | 1151 | False | 22/76 | `+worldquant.alpha040` (IR=0.1679, t=5.61) | `+worldquant.alpha044` (IR=0.1598, t=5.24) | `+worldquant.alpha016` (IR=0.1505, t=5.20) |
| trend | neutral | 3050 | False | 47/76 | `+worldquant.alpha040` (IR=0.2209, t=11.88) | `+worldquant.alpha044` (IR=0.1777, t=9.93) | `+worldquant.alpha094` (IR=0.1735, t=9.75) |
| trend | bull | 1144 | False | 29/76 | `+worldquant.alpha040` (IR=0.2754, t=9.78) | `+worldquant.alpha094` (IR=0.2393, t=8.40) | `+worldquant.alpha016` (IR=0.1937, t=7.20) |
| volatility | low | 2180 | False | 37/76 | `+worldquant.alpha040` (IR=0.2417, t=11.99) | `+worldquant.alpha094` (IR=0.1746, t=8.43) | `+worldquant.alpha044` (IR=0.1544, t=7.65) |
| volatility | normal | 1197 | False | 35/76 | `+worldquant.alpha040` (IR=0.2229, t=7.61) | `+worldquant.alpha025` (IR=0.1934, t=6.66) | `+worldquant.alpha016` (IR=0.1688, t=6.06) |
| volatility | high | 1849 | False | 34/76 | `+worldquant.alpha040` (IR=0.2054, t=9.19) | `+worldquant.alpha016` (IR=0.1987, t=8.56) | `+worldquant.alpha094` (IR=0.1929, t=8.97) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha025 | trend | Conditional | 0.1576 | bull | 0.1709 | 1144 | False |
| 2 | worldquant.alpha054 | trend | Conditional | 0.1357 | bull | -0.1213 | 1144 | False |
| 3 | worldquant.alpha035 | trend | Conditional | 0.1285 | bear | 0.1289 | 1151 | False |
| 4 | worldquant.alpha054 | liquidity | Regime-Reversal | 0.1277 | starved | -0.0824 | 1383 | False |
| 5 | worldquant.alpha101 | trend | Conditional | 0.1249 | bear | -0.1119 | 1151 | False |
| 6 | worldquant.alpha036 | trend | Conditional | 0.1225 | bull | 0.1588 | 1144 | False |
| 7 | worldquant.alpha083 | trend | Conditional | 0.1220 | bull | 0.1134 | 1144 | False |
| 8 | worldquant.alpha043 | trend | Conditional | 0.1133 | bear | 0.1115 | 1151 | False |
| 9 | worldquant.alpha045 | dispersion | Mixed / Moderate | 0.1128 | high | 0.0853 | 1611 | False |
| 10 | worldquant.alpha043 | liquidity | Regime-Reversal | 0.1119 | normal | 0.0763 | 2584 | False |
| 11 | worldquant.alpha031 | dispersion | Conditional | 0.1103 | high | 0.1251 | 1611 | False |
| 12 | worldquant.alpha094 | trend | Conditional | 0.1082 | bull | 0.2393 | 1144 | False |
| 13 | worldquant.alpha040 | trend | Conditional | 0.1075 | bull | 0.2754 | 1144 | False |
| 14 | worldquant.alpha002 | trend | Conditional | 0.1074 | bull | 0.1434 | 1144 | False |
| 15 | worldquant.alpha025 | volatility | Conditional | 0.1036 | normal | 0.1934 | 1197 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha040 | trend | bull | 0.2754 | 0.2754 | original | 1144 | 0.6049 |
| 2 | worldquant.alpha040 | liquidity | starved | 0.2474 | 0.2474 | original | 1383 | 0.5879 |
| 3 | worldquant.alpha040 | volatility | low | 0.2417 | 0.2417 | original | 2180 | 0.5991 |
| 4 | worldquant.alpha094 | trend | bull | 0.2393 | 0.2393 | original | 1144 | 0.5892 |
| 5 | worldquant.alpha040 | liquidity | normal | 0.2281 | 0.2281 | original | 2584 | 0.5937 |
| 6 | worldquant.alpha040 | volatility | normal | 0.2229 | 0.2229 | original | 1197 | 0.5764 |
| 7 | worldquant.alpha040 | dispersion | high | 0.2224 | 0.2224 | original | 1611 | 0.5847 |
| 8 | worldquant.alpha040 | trend | neutral | 0.2209 | 0.2209 | original | 3050 | 0.5875 |
| 9 | worldquant.alpha040 | dispersion | normal | 0.2206 | 0.2206 | original | 2046 | 0.5894 |
| 10 | worldquant.alpha040 | dispersion | low | 0.2200 | 0.2200 | original | 1688 | 0.5794 |
| 11 | worldquant.alpha040 | volatility | high | 0.2054 | 0.2054 | original | 1849 | 0.5765 |
| 12 | worldquant.alpha094 | liquidity | starved | 0.2003 | 0.2003 | original | 1383 | 0.5770 |
| 13 | worldquant.alpha016 | volatility | high | 0.1987 | 0.1987 | original | 1849 | 0.5895 |
| 14 | worldquant.alpha016 | trend | bull | 0.1937 | 0.1937 | original | 1144 | 0.5892 |
| 15 | worldquant.alpha025 | volatility | normal | 0.1934 | 0.1934 | original | 1197 | 0.5856 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
