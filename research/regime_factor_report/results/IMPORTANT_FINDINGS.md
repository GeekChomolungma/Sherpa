# Important Findings

This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.

## Dataset health

- Rows: **1312**; factors: **82**; dimensions: **4**.
- Missing/zero-sample metric rows: **16**.
- Factors with missing/zero-sample rows: **worldquant.alpha096**.
- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.

## Data-derived thresholds

- |IC_IR| median: **0.1030**; upper quartile: **0.1611**.
- IR-spread upper quartile: **0.1372**. This is used as the primary 'regime-sensitive' cutoff.
- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.

## Factor-level classification counts

- Regime-Reversal: **20**
- Conditional: **33**
- Stable: **0**
- Mixed / Moderate: **22**
- Weak / Noise: **6**
- Data Quality Issue: **1**

## Dimension-level classification counts

- Regime-Reversal: **22**
- Conditional: **46**
- Stable: **33**
- Mixed / Moderate: **135**
- Weak / Noise: **88**
- Data Quality Issue: **4**

## Most regime-sensitive factor/dimension pairs

| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |
|---:|---|---|---|---:|---|---:|---:|---|
| 1 | worldquant.alpha088 | trend | Conditional | 0.5889 | bull | 0.8124 | 54 | True |
| 2 | worldquant.alpha007 | liquidity | Regime-Reversal | 0.5277 | starved | -0.4466 | 559 | False |
| 3 | worldquant.alpha068 | trend | Regime-Reversal | 0.4209 | bull | -0.3427 | 54 | True |
| 4 | worldquant.alpha032 | trend | Conditional | 0.3841 | bull | 0.3768 | 54 | True |
| 5 | worldquant.alpha101 | trend | Regime-Reversal | 0.3812 | bull | 0.1942 | 54 | True |
| 6 | worldquant.alpha017 | liquidity | Conditional | 0.3443 | starved | 0.3285 | 578 | False |
| 7 | worldquant.alpha016 | trend | Conditional | 0.3361 | bull | 0.5957 | 54 | True |
| 8 | worldquant.alpha031 | trend | Regime-Reversal | 0.3328 | bull | -0.2217 | 54 | True |
| 9 | worldquant.alpha057 | trend | Regime-Reversal | 0.3281 | bull | -0.2520 | 54 | True |
| 10 | worldquant.alpha021 | liquidity | Regime-Reversal | 0.3123 | starved | -0.1974 | 571 | False |
| 11 | worldquant.alpha015 | trend | Conditional | 0.3087 | bull | 0.4174 | 54 | True |
| 12 | worldquant.alpha049 | trend | Regime-Reversal | 0.3039 | bear | 0.1765 | 924 | False |
| 13 | worldquant.alpha009 | trend | Regime-Reversal | 0.3023 | bull | -0.2060 | 54 | True |
| 14 | worldquant.alpha035 | trend | Regime-Reversal | 0.3016 | bear | 0.2089 | 923 | False |
| 15 | worldquant.alpha049 | liquidity | Conditional | 0.2928 | starved | 0.3222 | 578 | False |

## Strongest regime observations after excluding low-sample states

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |
|---:|---|---|---|---:|---:|---|---:|---:|
| 1 | worldquant.alpha007 | liquidity | starved | -0.4466 | 0.4466 | invert | 559 | 0.3131 |
| 2 | worldquant.alpha038 | liquidity | starved | 0.3854 | 0.3854 | original | 578 | 0.6574 |
| 3 | worldquant.alpha002 | liquidity | starved | 0.3598 | 0.3598 | original | 578 | 0.6851 |
| 4 | worldquant.alpha013 | dispersion | low | 0.3578 | 0.3578 | original | 700 | 0.6671 |
| 5 | worldquant.alpha044 | liquidity | starved | 0.3546 | 0.3546 | original | 578 | 0.6730 |
| 6 | worldquant.alpha013 | liquidity | normal | 0.3531 | 0.3531 | original | 1155 | 0.6632 |
| 7 | worldquant.alpha013 | liquidity | starved | 0.3523 | 0.3523 | original | 578 | 0.6453 |
| 8 | worldquant.alpha033 | liquidity | starved | 0.3475 | 0.3475 | original | 578 | 0.6488 |
| 9 | worldquant.alpha016 | liquidity | starved | 0.3453 | 0.3453 | original | 578 | 0.6661 |
| 10 | worldquant.alpha013 | volatility | high | 0.3435 | 0.3435 | original | 874 | 0.6533 |
| 11 | worldquant.alpha013 | trend | neutral | 0.3372 | 0.3372 | original | 1412 | 0.6516 |
| 12 | worldquant.alpha016 | liquidity | normal | 0.3360 | 0.3360 | original | 1155 | 0.6615 |
| 13 | worldquant.alpha016 | dispersion | low | 0.3353 | 0.3353 | original | 700 | 0.6714 |
| 14 | worldquant.alpha044 | liquidity | normal | 0.3347 | 0.3347 | original | 1155 | 0.6632 |
| 15 | worldquant.alpha016 | trend | neutral | 0.3334 | 0.3334 | original | 1412 | 0.6530 |

## Strong-looking results that are low-sample (treat cautiously)

| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |
|---:|---|---|---|---:|---:|---:|---:|
| 1 | worldquant.alpha088 | trend | bull | 0.8124 | 0.8124 | 54 | 0.0231 |
| 2 | worldquant.alpha016 | trend | bull | 0.5957 | 0.5957 | 54 | 0.0226 |
| 3 | worldquant.alpha044 | trend | bull | 0.5072 | 0.5072 | 54 | 0.0226 |
| 4 | worldquant.alpha013 | trend | bull | 0.4905 | 0.4905 | 54 | 0.0226 |
| 5 | worldquant.alpha055 | trend | bull | 0.4646 | 0.4646 | 54 | 0.0226 |
| 6 | worldquant.alpha026 | trend | bull | 0.4435 | 0.4435 | 54 | 0.0226 |
| 7 | worldquant.alpha015 | trend | bull | 0.4174 | 0.4174 | 54 | 0.0236 |
| 8 | worldquant.alpha050 | trend | bull | 0.3957 | 0.3957 | 54 | 0.0228 |
| 9 | worldquant.alpha032 | trend | bull | 0.3768 | 0.3768 | 54 | 0.0244 |
| 10 | worldquant.alpha068 | trend | bull | -0.3427 | 0.3427 | 54 | 0.0237 |

## Reading order

1. Start with `01_factor_overview.csv` to decide which factors deserve attention.
2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.
3. Open the matching file in `dimensions/` to compare every state side by side.
4. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.
5. Always check `low_sample` before acting on an extreme IC/IR.
