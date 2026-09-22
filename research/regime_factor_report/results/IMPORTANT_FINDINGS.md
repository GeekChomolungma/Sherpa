# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **1312**; factors: **82**; dimensions: **4**.
- Missing/zero-sample metric rows: **16**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1051**; upper quartile: **0.1952**.
- IR-spread upper quartile: **0.1749**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **31**
- Conditional: **19**
- Stable: **0**
- Mixed / Moderate: **28**
- Weak / Noise: **3**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **36**
- Conditional: **37**
- Stable: **34**
- Mixed / Moderate: **133**
- Weak / Noise: **84**
- Data Quality Issue: **4**

## Regime strategy matrix (Top alphas per state)

| Dimension | State | Samples | Low sample? | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |
|---|---|---:|:---:|---|---|---|
| dispersion | low | 255 | False | `+worldquant.alpha016` (IR=0.5118) | `+worldquant.alpha013` (IR=0.4232) | `+worldquant.alpha088` (IR=0.3909) |
| dispersion | normal | 362 | False | `+worldquant.alpha088` (IR=0.4642) | `+worldquant.alpha016` (IR=0.4286) | `+worldquant.alpha050` (IR=0.4137) |
| dispersion | high | 281 | False | `+worldquant.alpha016` (IR=0.4446) | `+worldquant.alpha013` (IR=0.4147) | `+worldquant.alpha088` (IR=0.4048) |
| liquidity | starved | 215 | False | `+worldquant.alpha016` (IR=0.5494) | `+worldquant.alpha038` (IR=0.4885) | `+worldquant.alpha050` (IR=0.4862) |
| liquidity | normal | 454 | False | `+worldquant.alpha016` (IR=0.5029) | `+worldquant.alpha088` (IR=0.4678) | `+worldquant.alpha044` (IR=0.4387) |
| liquidity | high | 229 | False | `+worldquant.alpha088` (IR=0.3439) | `+worldquant.alpha053` (IR=0.3240) | `+worldquant.alpha050` (IR=0.3166) |
| trend | bear | 258 | False | `+worldquant.alpha088` (IR=0.3968) | `+worldquant.alpha016` (IR=0.3826) | `+worldquant.alpha044` (IR=0.3565) |
| trend | neutral | 586 | False | `+worldquant.alpha016` (IR=0.4934) | `+worldquant.alpha013` (IR=0.4517) | `+worldquant.alpha088` (IR=0.4261) |
| trend | bull | 54 | True | `+worldquant.alpha088` (IR=0.5507) | `-worldquant.alpha054` (IR=-0.5184) | `+worldquant.alpha003` (IR=0.5138) |
| volatility | low | 302 | False | `+worldquant.alpha016` (IR=0.4723) | `+worldquant.alpha088` (IR=0.4583) | `+worldquant.alpha050` (IR=0.3750) |
| volatility | normal | 286 | False | `+worldquant.alpha016` (IR=0.5530) | `+worldquant.alpha044` (IR=0.4744) | `+worldquant.alpha088` (IR=0.4732) |
| volatility | high | 310 | False | `+worldquant.alpha016` (IR=0.3566) | `+worldquant.alpha050` (IR=0.3553) | `+worldquant.alpha088` (IR=0.3526) |

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha010 | trend | Regime-Reversal | 0.7524 | bull | -0.4747 | 54 | True |
| 2 | worldquant.alpha101 | trend | Regime-Reversal | 0.7289 | bull | 0.4700 | 54 | True |
| 3 | worldquant.alpha068 | trend | Regime-Reversal | 0.5903 | bull | -0.4733 | 54 | True |
| 4 | worldquant.alpha035 | trend | Regime-Reversal | 0.5879 | bull | -0.3256 | 54 | True |
| 5 | worldquant.alpha034 | trend | Regime-Reversal | 0.5600 | bull | -0.3477 | 54 | True |
| 6 | worldquant.alpha086 | trend | Regime-Reversal | 0.5586 | bull | -0.4038 | 54 | True |
| 7 | worldquant.alpha043 | liquidity | Regime-Reversal | 0.5535 | starved | -0.3997 | 215 | False |
| 8 | worldquant.alpha025 | trend | Regime-Reversal | 0.5360 | bull | -0.2877 | 54 | True |
| 9 | worldquant.alpha007 | liquidity | Regime-Reversal | 0.5110 | starved | -0.3241 | 215 | False |
| 10 | worldquant.alpha017 | trend | Regime-Reversal | 0.4894 | bull | -0.2761 | 54 | True |
| 11 | worldquant.alpha054 | trend | Conditional | 0.4788 | bull | -0.5184 | 54 | True |
| 12 | worldquant.alpha031 | trend | Regime-Reversal | 0.4365 | bull | -0.3647 | 54 | True |
| 13 | worldquant.alpha062 | trend | Regime-Reversal | 0.4211 | bear | 0.2418 | 258 | False |
| 14 | worldquant.alpha078 | trend | Regime-Reversal | 0.4190 | bull | -0.2166 | 54 | True |
| 15 | worldquant.alpha095 | trend | Conditional | 0.4129 | bull | -0.4128 | 54 | True |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha016 | volatility | normal | 0.5530 | 0.5530 | original | 286 | 0.6923 |
| 2 | worldquant.alpha016 | liquidity | starved | 0.5494 | 0.5494 | original | 215 | 0.6884 |
| 3 | worldquant.alpha016 | dispersion | low | 0.5118 | 0.5118 | original | 255 | 0.6627 |
| 4 | worldquant.alpha016 | liquidity | normal | 0.5029 | 0.5029 | original | 454 | 0.6718 |
| 5 | worldquant.alpha016 | trend | neutral | 0.4934 | 0.4934 | original | 586 | 0.6689 |
| 6 | worldquant.alpha038 | liquidity | starved | 0.4885 | 0.4885 | original | 215 | 0.6651 |
| 7 | worldquant.alpha050 | liquidity | starved | 0.4862 | 0.4862 | original | 215 | 0.6605 |
| 8 | worldquant.alpha044 | volatility | normal | 0.4744 | 0.4744 | original | 286 | 0.6818 |
| 9 | worldquant.alpha088 | volatility | normal | 0.4732 | 0.4732 | original | 285 | 0.7053 |
| 10 | worldquant.alpha016 | volatility | low | 0.4723 | 0.4723 | original | 302 | 0.6457 |
| 11 | worldquant.alpha088 | liquidity | normal | 0.4678 | 0.4678 | original | 454 | 0.7004 |
| 12 | worldquant.alpha088 | dispersion | normal | 0.4642 | 0.4642 | original | 362 | 0.6796 |
| 13 | worldquant.alpha015 | liquidity | starved | 0.4619 | 0.4619 | original | 215 | 0.6605 |
| 14 | worldquant.alpha088 | volatility | low | 0.4583 | 0.4583 | original | 302 | 0.6887 |
| 15 | worldquant.alpha050 | volatility | normal | 0.4536 | 0.4536 | original | 286 | 0.6678 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha088 | trend | bull | 0.5507 | 0.5507 | 54 | 0.0602 |
| 2 | worldquant.alpha054 | trend | bull | -0.5184 | 0.5184 | 54 | 0.0601 |
| 3 | worldquant.alpha003 | trend | bull | 0.5138 | 0.5138 | 54 | 0.0601 |
| 4 | worldquant.alpha010 | trend | bull | -0.4747 | 0.4747 | 54 | 0.0601 |
| 5 | worldquant.alpha068 | trend | bull | -0.4733 | 0.4733 | 54 | 0.0601 |
| 6 | worldquant.alpha101 | trend | bull | 0.4700 | 0.4700 | 54 | 0.0601 |
| 7 | worldquant.alpha016 | trend | bull | 0.4361 | 0.4361 | 54 | 0.0601 |
| 8 | worldquant.alpha050 | trend | bull | 0.4321 | 0.4321 | 54 | 0.0601 |
| 9 | worldquant.alpha095 | trend | bull | -0.4128 | 0.4128 | 54 | 0.0601 |
| 10 | worldquant.alpha086 | trend | bull | -0.4038 | 0.4038 | 54 | 0.0601 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.
5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
6. Always check `low_sample` before acting on an extreme IC/IR.
