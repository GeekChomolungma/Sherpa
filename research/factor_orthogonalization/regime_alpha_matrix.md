# Regime × Alpha 因子矩阵

`+`：按 Alpha 原值同向排序；`-`：按 Alpha 原值反向排序。

| Dimension | State | Factor 1 | Factor 2 | Factor 3 |
|---|---|---|---|---|
| `trend` | `bear` | `+alpha088` | `+alpha044` | `+alpha027` |
| `trend` | `neutral` | `+alpha088` | `+alpha050` | `+alpha013` |
| `trend` | `bull*` | `+alpha088` | `+alpha003` | `-alpha068` |
| `volatility` | `low` | `+alpha088` | `+alpha050` | `+alpha013` |
| `volatility` | `normal` | `+alpha088` | `+alpha044` | `+alpha050` |
| `volatility` | `high` | `+alpha088` | `+alpha027` | `+alpha013` |
| `liquidity` | `starved` | `+alpha038` | `+alpha050` | `+alpha013` |
| `liquidity` | `normal` | `+alpha088` | `+alpha044` | `+alpha050` |
| `liquidity` | `high` | `+alpha053` | `+alpha088` | `+alpha027` |
| `dispersion` | `low` | `+alpha088` | `+alpha044` | `+alpha050` |
| `dispersion` | `normal` | `+alpha088` | `+alpha044` | `+alpha050` |
| `dispersion` | `high` | `+alpha088` | `+alpha050` | `+alpha013` |

> `trend = bull` 仅 54 个样本，属于低样本状态；符号方向保留，但实际使用时应降低置信度。
