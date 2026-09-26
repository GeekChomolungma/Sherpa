# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **1248**; factors: **78**; dimensions: **4**.
- Missing/zero-sample metric rows: **16**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0870**; upper quartile: **0.1412**.
- IR-spread upper quartile: **0.0660**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **2**
- Conditional: **39**
- Stable: **0**
- Mixed / Moderate: **15**
- Weak / Noise: **21**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **2**
- Conditional: **50**
- Stable: **35**
- Mixed / Moderate: **106**
- Weak / Noise: **115**
- Data Quality Issue: **4**

## Regime strategy matrix (Top alphas per state)

Only alphas with |t_stat| >= 3 are eligible; eligible alphas are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.

| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---:|---|---|---|
| dispersion | low | 4091 | False | 53/77 | `+worldquant.alpha033` (IR=0.2561, t=15.43) | `+worldquant.alpha083` (IR=0.2379, t=14.27) | `+worldquant.alpha038` (IR=0.2355, t=14.13) |
| dispersion | normal | 5192 | False | 54/77 | `+worldquant.alpha033` (IR=0.2492, t=17.89) | `+worldquant.alpha038` (IR=0.2229, t=16.10) | `+worldquant.alpha009` (IR=0.2156, t=15.47) |
| dispersion | high | 4095 | False | 53/77 | `+worldquant.alpha033` (IR=0.2293, t=14.40) | `+worldquant.alpha038` (IR=0.2105, t=13.12) | `+worldquant.alpha034` (IR=0.1919, t=12.06) |
| liquidity | starved | 3345 | False | 59/77 | `+worldquant.alpha033` (IR=0.2670, t=15.12) | `+worldquant.alpha094` (IR=0.2605, t=16.05) | `+worldquant.alpha038` (IR=0.2564, t=14.42) |
| liquidity | normal | 6485 | False | 55/77 | `+worldquant.alpha033` (IR=0.2633, t=20.29) | `+worldquant.alpha038` (IR=0.2376, t=18.69) | `+worldquant.alpha009` (IR=0.2196, t=17.20) |
| liquidity | high | 3548 | False | 48/77 | `+worldquant.alpha033` (IR=0.1957, t=11.53) | `+worldquant.alpha083` (IR=0.1844, t=10.68) | `+worldquant.alpha057` (IR=0.1733, t=10.00) |
| trend | bear | 5367 | False | 56/77 | `+worldquant.alpha033` (IR=0.2536, t=17.00) | `+worldquant.alpha038` (IR=0.2327, t=16.13) | `+worldquant.alpha009` (IR=0.2165, t=15.04) |
| trend | neutral | 7821 | False | 61/77 | `+worldquant.alpha033` (IR=0.2376, t=20.60) | `+worldquant.alpha038` (IR=0.2156, t=18.95) | `+worldquant.alpha083` (IR=0.2041, t=17.81) |
| trend | bull | 190 | True | 26/77 | `+worldquant.alpha040` (IR=0.5841, t=7.48) | `+worldquant.alpha016` (IR=0.4475, t=6.67) | `+worldquant.alpha094` (IR=0.4360, t=5.06) |
| volatility | low | 5143 | False | 55/77 | `+worldquant.alpha033` (IR=0.2290, t=15.30) | `+worldquant.alpha009` (IR=0.2031, t=13.46) | `+worldquant.alpha038` (IR=0.2027, t=13.84) |
| volatility | normal | 3492 | False | 53/77 | `+worldquant.alpha033` (IR=0.2416, t=14.00) | `+worldquant.alpha038` (IR=0.2319, t=12.90) | `-worldquant.alpha101` (IR=-0.2074, t=-11.35) |
| volatility | high | 4716 | False | 51/77 | `+worldquant.alpha033` (IR=0.2675, t=17.68) | `+worldquant.alpha038` (IR=0.2426, t=16.27) | `+worldquant.alpha009` (IR=0.2277, t=15.14) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha040 | trend | Conditional | 0.4346 | bull | 0.5841 | 190 | True |
| 2 | worldquant.alpha016 | trend | Conditional | 0.3467 | bull | 0.4475 | 190 | True |
| 3 | worldquant.alpha015 | trend | Conditional | 0.3432 | bull | 0.3982 | 190 | True |
| 4 | worldquant.alpha073 | trend | Conditional | 0.3324 | bull | 0.4187 | 190 | True |
| 5 | worldquant.alpha026 | trend | Conditional | 0.3301 | bull | 0.4050 | 190 | True |
| 6 | worldquant.alpha055 | trend | Conditional | 0.3153 | bull | 0.4007 | 190 | True |
| 7 | worldquant.alpha044 | trend | Conditional | 0.2811 | bull | 0.3760 | 190 | True |
| 8 | worldquant.alpha013 | trend | Conditional | 0.2782 | bull | 0.3468 | 190 | True |
| 9 | worldquant.alpha094 | trend | Conditional | 0.2706 | bull | 0.4360 | 190 | True |
| 10 | worldquant.alpha054 | trend | Regime-Reversal | 0.2682 | bull | -0.1870 | 190 | True |
| 11 | worldquant.alpha003 | trend | Conditional | 0.2617 | bull | 0.3090 | 190 | True |
| 12 | worldquant.alpha101 | trend | Conditional | 0.2318 | bear | -0.2115 | 5367 | False |
| 13 | worldquant.alpha002 | trend | Conditional | 0.2309 | bull | 0.2936 | 190 | True |
| 14 | worldquant.alpha050 | trend | Conditional | 0.2276 | bull | 0.3204 | 190 | True |
| 15 | worldquant.alpha030 | trend | Regime-Reversal | 0.2189 | neutral | 0.1313 | 7821 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha033 | volatility | high | 0.2675 | 0.2675 | original | 4716 | 0.6132 |
| 2 | worldquant.alpha033 | liquidity | starved | 0.2670 | 0.2670 | original | 3345 | 0.6227 |
| 3 | worldquant.alpha033 | liquidity | normal | 0.2633 | 0.2633 | original | 6485 | 0.6168 |
| 4 | worldquant.alpha094 | liquidity | starved | 0.2605 | 0.2605 | original | 3340 | 0.6296 |
| 5 | worldquant.alpha038 | liquidity | starved | 0.2564 | 0.2564 | original | 3345 | 0.6245 |
| 6 | worldquant.alpha033 | dispersion | low | 0.2561 | 0.2561 | original | 4091 | 0.6094 |
| 7 | worldquant.alpha033 | trend | bear | 0.2536 | 0.2536 | original | 5367 | 0.6128 |
| 8 | worldquant.alpha033 | dispersion | normal | 0.2492 | 0.2492 | original | 5192 | 0.6123 |
| 9 | worldquant.alpha038 | volatility | high | 0.2426 | 0.2426 | original | 4716 | 0.6158 |
| 10 | worldquant.alpha101 | liquidity | starved | -0.2416 | 0.2416 | invert | 3345 | 0.3800 |
| 11 | worldquant.alpha033 | volatility | normal | 0.2416 | 0.2416 | original | 3492 | 0.6171 |
| 12 | worldquant.alpha083 | dispersion | low | 0.2379 | 0.2379 | original | 4091 | 0.5967 |
| 13 | worldquant.alpha033 | trend | neutral | 0.2376 | 0.2376 | original | 7821 | 0.6098 |
| 14 | worldquant.alpha038 | liquidity | normal | 0.2376 | 0.2376 | original | 6485 | 0.6096 |
| 15 | worldquant.alpha038 | dispersion | low | 0.2355 | 0.2355 | original | 4091 | 0.6101 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha040 | trend | bull | 0.5841 | 0.5841 | 190 | 0.0142 |
| 2 | worldquant.alpha016 | trend | bull | 0.4475 | 0.4475 | 190 | 0.0142 |
| 3 | worldquant.alpha094 | trend | bull | 0.4360 | 0.4360 | 190 | 0.0142 |
| 4 | worldquant.alpha073 | trend | bull | 0.4187 | 0.4187 | 190 | 0.0142 |
| 5 | worldquant.alpha026 | trend | bull | 0.4050 | 0.4050 | 190 | 0.0142 |
| 6 | worldquant.alpha055 | trend | bull | 0.4007 | 0.4007 | 190 | 0.0142 |
| 7 | worldquant.alpha015 | trend | bull | 0.3982 | 0.3982 | 190 | 0.0147 |
| 8 | worldquant.alpha044 | trend | bull | 0.3760 | 0.3760 | 190 | 0.0142 |
| 9 | worldquant.alpha010 | trend | bull | 0.3677 | 0.3677 | 190 | 0.0142 |
| 10 | worldquant.alpha037 | trend | bull | 0.3640 | 0.3640 | 190 | 0.0143 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
