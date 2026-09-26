# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **936**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **13**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0749**; upper quartile: **0.1148**.
- IR-spread upper quartile: **0.0812**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **11**
- Conditional: **25**
- Stable: **0**
- Mixed / Moderate: **26**
- Weak / Noise: **15**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **11**
- Conditional: **36**
- Stable: **39**
- Mixed / Moderate: **121**
- Weak / Noise: **101**
- Data Quality Issue: **4**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 1309 | False | 39/77 | `+worldquant.alpha040` (IR=0.3087, t=11.07) | `+worldquant.alpha044` (IR=0.2518, t=8.77) | `+worldquant.alpha016` (IR=0.2427, t=8.37) |
| dispersion | normal | 1638 | False | 40/77 | `+worldquant.alpha094` (IR=0.2873, t=11.83) | `+worldquant.alpha016` (IR=0.2466, t=10.29) | `+worldquant.alpha044` (IR=0.2442, t=9.81) |
| dispersion | high | 1306 | False | 27/77 | `+worldquant.alpha016` (IR=0.2000, t=7.61) | `+worldquant.alpha040` (IR=0.1911, t=6.63) | `+worldquant.alpha094` (IR=0.1857, t=7.45) |
| liquidity | starved | 1108 | False | 42/77 | `+worldquant.alpha094` (IR=0.3395, t=11.04) | `+worldquant.alpha040` (IR=0.3024, t=10.63) | `+worldquant.alpha016` (IR=0.3009, t=9.67) |
| liquidity | normal | 2040 | False | 40/77 | `+worldquant.alpha040` (IR=0.2462, t=11.67) | `+worldquant.alpha016` (IR=0.2456, t=11.31) | `+worldquant.alpha094` (IR=0.2315, t=11.41) |
| liquidity | high | 1105 | False | 25/77 | `+worldquant.alpha040` (IR=0.1873, t=6.21) | `+worldquant.alpha036` (IR=0.1781, t=5.68) | `+worldquant.alpha044` (IR=0.1777, t=5.99) |
| trend | bear | 1207 | False | 33/77 | `+worldquant.alpha044` (IR=0.2399, t=8.19) | `+worldquant.alpha094` (IR=0.2241, t=7.76) | `+worldquant.alpha016` (IR=0.2193, t=7.40) |
| trend | neutral | 2876 | False | 46/77 | `+worldquant.alpha040` (IR=0.2574, t=14.37) | `+worldquant.alpha094` (IR=0.2515, t=13.45) | `+worldquant.alpha016` (IR=0.2371, t=12.98) |
| trend | bull | 170 | True | 3/77 | `+worldquant.alpha036` (IR=0.2764, t=3.76) | `+worldquant.alpha003` (IR=0.2493, t=3.39) | `+worldquant.alpha040` (IR=0.2245, t=3.29) |
| volatility | low | 1646 | False | 33/77 | `+worldquant.alpha040` (IR=0.2681, t=11.51) | `+worldquant.alpha016` (IR=0.2612, t=10.92) | `+worldquant.alpha094` (IR=0.2398, t=10.04) |
| volatility | normal | 1013 | False | 38/77 | `+worldquant.alpha040` (IR=0.2459, t=7.92) | `+worldquant.alpha094` (IR=0.2322, t=7.76) | `+worldquant.alpha044` (IR=0.2195, t=6.92) |
| volatility | high | 1475 | False | 34/77 | `+worldquant.alpha094` (IR=0.2387, t=9.98) | `+worldquant.alpha040` (IR=0.2158, t=8.55) | `+worldquant.alpha044` (IR=0.2091, t=8.11) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha035 | trend | Regime-Reversal | 0.3360 | bear | 0.1805 | 1207 | False |
| 2 | worldquant.alpha101 | trend | Regime-Reversal | 0.3029 | bull | 0.1569 | 170 | True |
| 3 | worldquant.alpha065 | trend | Regime-Reversal | 0.2773 | bear | 0.1992 | 1207 | False |
| 4 | worldquant.alpha084 | trend | Regime-Reversal | 0.1847 | bear | 0.1307 | 1207 | False |
| 5 | worldquant.alpha007 | liquidity | Regime-Reversal | 0.1830 | high | 0.0919 | 1105 | False |
| 6 | worldquant.alpha099 | trend | Regime-Reversal | 0.1752 | bull | -0.1161 | 170 | True |
| 7 | worldquant.alpha043 | liquidity | Regime-Reversal | 0.1746 | high | 0.0966 | 1105 | False |
| 8 | worldquant.alpha073 | liquidity | Conditional | 0.1727 | starved | 0.2458 | 1108 | False |
| 9 | worldquant.alpha094 | liquidity | Conditional | 0.1719 | starved | 0.3395 | 1108 | False |
| 10 | worldquant.alpha044 | trend | Conditional | 0.1681 | bear | 0.2399 | 1207 | False |
| 11 | worldquant.alpha016 | liquidity | Conditional | 0.1651 | starved | 0.3009 | 1108 | False |
| 12 | worldquant.alpha086 | trend | Regime-Reversal | 0.1560 | bull | -0.0995 | 170 | True |
| 13 | worldquant.alpha007 | trend | Conditional | 0.1548 | bull | -0.1268 | 170 | True |
| 14 | worldquant.alpha029 | liquidity | Conditional | 0.1508 | starved | 0.2498 | 1108 | False |
| 15 | worldquant.alpha036 | trend | Conditional | 0.1356 | bull | 0.2764 | 170 | True |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha094 | liquidity | starved | 0.3395 | 0.3395 | original | 1108 | 0.6363 |
| 2 | worldquant.alpha040 | dispersion | low | 0.3087 | 0.3087 | original | 1309 | 0.6142 |
| 3 | worldquant.alpha040 | liquidity | starved | 0.3024 | 0.3024 | original | 1108 | 0.6146 |
| 4 | worldquant.alpha016 | liquidity | starved | 0.3009 | 0.3009 | original | 1108 | 0.6273 |
| 5 | worldquant.alpha094 | dispersion | normal | 0.2873 | 0.2873 | original | 1638 | 0.6227 |
| 6 | worldquant.alpha040 | volatility | low | 0.2681 | 0.2681 | original | 1646 | 0.6051 |
| 7 | worldquant.alpha016 | volatility | low | 0.2612 | 0.2612 | original | 1646 | 0.6112 |
| 8 | worldquant.alpha044 | liquidity | starved | 0.2593 | 0.2593 | original | 1108 | 0.5912 |
| 9 | worldquant.alpha040 | trend | neutral | 0.2574 | 0.2574 | original | 2876 | 0.5921 |
| 10 | worldquant.alpha044 | dispersion | low | 0.2518 | 0.2518 | original | 1309 | 0.5844 |
| 11 | worldquant.alpha094 | trend | neutral | 0.2515 | 0.2515 | original | 2876 | 0.5970 |
| 12 | worldquant.alpha029 | liquidity | starved | 0.2498 | 0.2498 | original | 1108 | 0.6002 |
| 13 | worldquant.alpha016 | dispersion | normal | 0.2466 | 0.2466 | original | 1638 | 0.6020 |
| 14 | worldquant.alpha040 | liquidity | normal | 0.2462 | 0.2462 | original | 2040 | 0.5951 |
| 15 | worldquant.alpha040 | volatility | normal | 0.2459 | 0.2459 | original | 1013 | 0.5893 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha036 | trend | bull | 0.2764 | 0.2764 | 170 | 0.0407 |
| 2 | worldquant.alpha003 | trend | bull | 0.2493 | 0.2493 | 170 | 0.0400 |
| 3 | worldquant.alpha040 | trend | bull | 0.2245 | 0.2245 | 170 | 0.0400 |
| 4 | worldquant.alpha024 | trend | bull | 0.2231 | 0.2231 | 170 | 0.0407 |
| 5 | worldquant.alpha050 | trend | bull | 0.2039 | 0.2039 | 170 | 0.0400 |
| 6 | worldquant.alpha016 | trend | bull | 0.1980 | 0.1980 | 170 | 0.0400 |
| 7 | worldquant.alpha094 | trend | bull | 0.1826 | 0.1826 | 170 | 0.0400 |
| 8 | worldquant.alpha039 | trend | bull | 0.1825 | 0.1825 | 170 | 0.0412 |
| 9 | worldquant.alpha029 | trend | bull | 0.1823 | 0.1823 | 170 | 0.0400 |
| 10 | worldquant.alpha073 | trend | bull | 0.1652 | 0.1652 | 170 | 0.0400 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
