# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **1248**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **16**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1198**; upper quartile: **0.1769**.
- IR-spread upper quartile: **0.0899**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **1**
- Conditional: **37**
- Stable: **0**
- Mixed / Moderate: **19**
- Weak / Noise: **20**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **1**
- Conditional: **55**
- Stable: **33**
- Mixed / Moderate: **107**
- Weak / Noise: **112**
- Data Quality Issue: **4**

## Regime strategy matrix (Top alphas per state)

| Dimension | State | Samples | Low sample? | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---|---|---|
| dispersion | low | 1788 | False | `+worldquant.alpha094` (IR=0.3515) | `+worldquant.alpha038` (IR=0.2995) | `-worldquant.alpha101` (IR=-0.2912) |
| dispersion | normal | 2243 | False | `+worldquant.alpha094` (IR=0.3057) | `+worldquant.alpha040` (IR=0.3049) | `+worldquant.alpha038` (IR=0.2657) |
| dispersion | high | 1777 | False | `+worldquant.alpha033` (IR=0.2324) | `+worldquant.alpha094` (IR=0.2312) | `+worldquant.alpha038` (IR=0.2110) |
| liquidity | starved | 1501 | False | `+worldquant.alpha094` (IR=0.4275) | `+worldquant.alpha038` (IR=0.3471) | `+worldquant.alpha040` (IR=0.3435) |
| liquidity | normal | 2820 | False | `+worldquant.alpha033` (IR=0.2763) | `-worldquant.alpha101` (IR=-0.2600) | `+worldquant.alpha038` (IR=0.2590) |
| liquidity | high | 1487 | False | `+worldquant.alpha094` (IR=0.2565) | `+worldquant.alpha040` (IR=0.2462) | `+worldquant.alpha016` (IR=0.2064) |
| trend | bear | 1642 | False | `-worldquant.alpha101` (IR=-0.2692) | `+worldquant.alpha094` (IR=0.2486) | `+worldquant.alpha040` (IR=0.2354) |
| trend | neutral | 3868 | False | `+worldquant.alpha094` (IR=0.3086) | `+worldquant.alpha033` (IR=0.2770) | `+worldquant.alpha038` (IR=0.2707) |
| trend | bull | 298 | True | `+worldquant.alpha040` (IR=0.5341) | `+worldquant.alpha094` (IR=0.4012) | `+worldquant.alpha016` (IR=0.3713) |
| volatility | low | 2324 | False | `+worldquant.alpha094` (IR=0.3113) | `+worldquant.alpha040` (IR=0.2900) | `+worldquant.alpha033` (IR=0.2619) |
| volatility | normal | 1377 | False | `+worldquant.alpha038` (IR=0.2940) | `+worldquant.alpha033` (IR=0.2868) | `-worldquant.alpha101` (IR=-0.2820) |
| volatility | high | 1988 | False | `+worldquant.alpha094` (IR=0.2894) | `+worldquant.alpha038` (IR=0.2497) | `+worldquant.alpha033` (IR=0.2481) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha040 | trend | Conditional | 0.2987 | bull | 0.5341 | 298 | True |
| 2 | worldquant.alpha007 | liquidity | Regime-Reversal | 0.2585 | high | 0.1426 | 1487 | False |
| 3 | worldquant.alpha101 | liquidity | Conditional | 0.1984 | starved | -0.3201 | 1501 | False |
| 4 | worldquant.alpha032 | liquidity | Conditional | 0.1971 | starved | 0.2850 | 1459 | False |
| 5 | worldquant.alpha025 | trend | Conditional | 0.1965 | bull | 0.3208 | 298 | True |
| 6 | worldquant.alpha017 | liquidity | Conditional | 0.1958 | starved | 0.2276 | 1501 | False |
| 7 | worldquant.alpha054 | trend | Mixed / Moderate | 0.1952 | bull | -0.1400 | 298 | True |
| 8 | worldquant.alpha055 | trend | Conditional | 0.1901 | bull | 0.3262 | 298 | True |
| 9 | worldquant.alpha101 | trend | Conditional | 0.1884 | bear | -0.2692 | 1642 | False |
| 10 | worldquant.alpha066 | liquidity | Conditional | 0.1809 | starved | 0.2599 | 1501 | False |
| 11 | worldquant.alpha026 | trend | Conditional | 0.1805 | bull | 0.3192 | 298 | True |
| 12 | worldquant.alpha037 | trend | Conditional | 0.1793 | bull | 0.3079 | 298 | True |
| 13 | worldquant.alpha065 | trend | Conditional | 0.1790 | bull | 0.3014 | 298 | True |
| 14 | worldquant.alpha073 | liquidity | Conditional | 0.1786 | starved | 0.2755 | 1501 | False |
| 15 | worldquant.alpha094 | liquidity | Conditional | 0.1771 | starved | 0.4275 | 1501 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha094 | liquidity | starved | 0.4275 | 0.4275 | original | 1501 | 0.6742 |
| 2 | worldquant.alpha094 | dispersion | low | 0.3515 | 0.3515 | original | 1788 | 0.6331 |
| 3 | worldquant.alpha038 | liquidity | starved | 0.3471 | 0.3471 | original | 1501 | 0.6402 |
| 4 | worldquant.alpha040 | liquidity | starved | 0.3435 | 0.3435 | original | 1501 | 0.6442 |
| 5 | worldquant.alpha029 | liquidity | starved | 0.3240 | 0.3240 | original | 1501 | 0.6262 |
| 6 | worldquant.alpha101 | liquidity | starved | -0.3201 | 0.3201 | invert | 1501 | 0.3644 |
| 7 | worldquant.alpha033 | liquidity | starved | 0.3152 | 0.3152 | original | 1501 | 0.6289 |
| 8 | worldquant.alpha094 | volatility | low | 0.3113 | 0.3113 | original | 2324 | 0.6244 |
| 9 | worldquant.alpha094 | trend | neutral | 0.3086 | 0.3086 | original | 3868 | 0.6269 |
| 10 | worldquant.alpha094 | dispersion | normal | 0.3057 | 0.3057 | original | 2243 | 0.6313 |
| 11 | worldquant.alpha040 | dispersion | normal | 0.3049 | 0.3049 | original | 2243 | 0.6340 |
| 12 | worldquant.alpha044 | liquidity | starved | 0.3014 | 0.3014 | original | 1501 | 0.6196 |
| 13 | worldquant.alpha038 | dispersion | low | 0.2995 | 0.2995 | original | 1788 | 0.6264 |
| 14 | worldquant.alpha038 | volatility | normal | 0.2940 | 0.2940 | original | 1377 | 0.6333 |
| 15 | worldquant.alpha101 | dispersion | low | -0.2912 | 0.2912 | invert | 1788 | 0.3736 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha040 | trend | bull | 0.5341 | 0.5341 | 298 | 0.0513 |
| 2 | worldquant.alpha094 | trend | bull | 0.4012 | 0.4012 | 298 | 0.0513 |
| 3 | worldquant.alpha016 | trend | bull | 0.3713 | 0.3713 | 298 | 0.0513 |
| 4 | worldquant.alpha044 | trend | bull | 0.3323 | 0.3323 | 298 | 0.0513 |
| 5 | worldquant.alpha055 | trend | bull | 0.3262 | 0.3262 | 298 | 0.0513 |
| 6 | worldquant.alpha025 | trend | bull | 0.3208 | 0.3208 | 298 | 0.0513 |
| 7 | worldquant.alpha026 | trend | bull | 0.3192 | 0.3192 | 298 | 0.0513 |
| 8 | worldquant.alpha073 | trend | bull | 0.3106 | 0.3106 | 298 | 0.0513 |
| 9 | worldquant.alpha037 | trend | bull | 0.3079 | 0.3079 | 298 | 0.0520 |
| 10 | worldquant.alpha061 | trend | bull | 0.3074 | 0.3074 | 298 | 0.0520 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
