# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **1312**; factors: **82**; dimensions: **4**.
- Missing/zero-sample metric rows: **16**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.0742**; upper quartile: **0.1229**.
- IR-spread upper quartile: **0.1375**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **21**
- Conditional: **40**
- Stable: **0**
- Mixed / Moderate: **19**
- Weak / Noise: **1**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **26**
- Conditional: **53**
- Stable: **32**
- Mixed / Moderate: **142**
- Weak / Noise: **71**
- Data Quality Issue: **4**

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha009 | trend | Conditional | 0.5853 | bull | -0.5581 | 52 | True |
| 2 | worldquant.alpha068 | trend | Regime-Reversal | 0.5030 | bull | -0.4650 | 52 | True |
| 3 | worldquant.alpha010 | trend | Conditional | 0.4956 | bull | -0.5054 | 52 | True |
| 4 | worldquant.alpha042 | trend | Conditional | 0.4911 | bull | -0.5443 | 52 | True |
| 5 | worldquant.alpha049 | trend | Regime-Reversal | 0.4841 | bull | -0.3290 | 52 | True |
| 6 | worldquant.alpha037 | trend | Regime-Reversal | 0.4822 | bull | -0.3343 | 52 | True |
| 7 | worldquant.alpha007 | liquidity | Regime-Reversal | 0.4694 | starved | -0.3608 | 545 | False |
| 8 | worldquant.alpha101 | trend | Regime-Reversal | 0.4648 | bull | 0.3797 | 52 | True |
| 9 | worldquant.alpha031 | trend | Regime-Reversal | 0.4608 | bull | -0.3708 | 52 | True |
| 10 | worldquant.alpha025 | trend | Regime-Reversal | 0.4420 | bull | -0.3699 | 52 | True |
| 11 | worldquant.alpha024 | trend | Conditional | 0.4332 | bull | -0.4364 | 52 | True |
| 12 | worldquant.alpha034 | trend | Regime-Reversal | 0.4081 | bull | -0.3304 | 52 | True |
| 13 | worldquant.alpha051 | trend | Regime-Reversal | 0.4074 | bull | -0.2592 | 52 | True |
| 14 | worldquant.alpha094 | trend | Conditional | 0.3790 | bull | -0.3794 | 52 | True |
| 15 | worldquant.alpha054 | trend | Conditional | 0.3663 | bull | -0.4262 | 52 | True |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha007 | liquidity | starved | -0.3608 | 0.3608 | invert | 545 | 0.3321 |
| 2 | worldquant.alpha026 | liquidity | starved | 0.3039 | 0.3039 | original | 576 | 0.6111 |
| 3 | worldquant.alpha016 | volatility | low | 0.2849 | 0.2849 | original | 822 | 0.6204 |
| 4 | worldquant.alpha016 | dispersion | low | 0.2753 | 0.2753 | original | 697 | 0.6385 |
| 5 | worldquant.alpha033 | liquidity | starved | 0.2738 | 0.2738 | original | 576 | 0.5990 |
| 6 | worldquant.alpha038 | liquidity | starved | 0.2707 | 0.2707 | original | 576 | 0.6128 |
| 7 | worldquant.alpha013 | dispersion | low | 0.2672 | 0.2672 | original | 696 | 0.6293 |
| 8 | worldquant.alpha050 | dispersion | low | 0.2643 | 0.2643 | original | 681 | 0.6270 |
| 9 | worldquant.alpha044 | liquidity | normal | 0.2598 | 0.2598 | original | 1151 | 0.6377 |
| 10 | worldquant.alpha020 | liquidity | starved | 0.2595 | 0.2595 | original | 576 | 0.6059 |
| 11 | worldquant.alpha016 | trend | neutral | 0.2588 | 0.2588 | original | 1407 | 0.6311 |
| 12 | worldquant.alpha088 | liquidity | normal | 0.2588 | 0.2588 | original | 1106 | 0.6248 |
| 13 | worldquant.alpha016 | liquidity | normal | 0.2582 | 0.2582 | original | 1151 | 0.6325 |
| 14 | worldquant.alpha088 | volatility | normal | 0.2568 | 0.2568 | original | 680 | 0.6265 |
| 15 | worldquant.alpha013 | trend | neutral | 0.2480 | 0.2480 | original | 1407 | 0.6269 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha009 | trend | bull | -0.5581 | 0.5581 | 52 | 0.0218 |
| 2 | worldquant.alpha042 | trend | bull | -0.5443 | 0.5443 | 52 | 0.0218 |
| 3 | worldquant.alpha088 | trend | bull | 0.5125 | 0.5125 | 52 | 0.0225 |
| 4 | worldquant.alpha010 | trend | bull | -0.5054 | 0.5054 | 52 | 0.0218 |
| 5 | worldquant.alpha068 | trend | bull | -0.4650 | 0.4650 | 52 | 0.0231 |
| 6 | worldquant.alpha024 | trend | bull | -0.4364 | 0.4364 | 52 | 0.0232 |
| 7 | worldquant.alpha054 | trend | bull | -0.4262 | 0.4262 | 52 | 0.0218 |
| 8 | worldquant.alpha061 | trend | bull | -0.4241 | 0.4241 | 52 | 0.0231 |
| 9 | worldquant.alpha050 | trend | bull | 0.4183 | 0.4183 | 52 | 0.0224 |
| 10 | worldquant.alpha003 | trend | bull | 0.3919 | 0.3919 | 52 | 0.0218 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
5. Always check `low_sample` before acting on an extreme IC/IR.
