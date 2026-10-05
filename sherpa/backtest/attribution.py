"""策略收益的风格归因和分期稳定性：回答"赚的钱是不是选币能力，还是押了某种风格 / 只在某几个季度赚"。

关卡3（`research/friction_test/run_friction.py`）用它给每个 (case, 映射, 调仓频率) 出 `05_style_attribution.csv`
和 `06_quarterly.csv`。

**风格归因**：时间序列回归 `r_t = α + Σ_j β_j · f_{j,t} + ε_t`，`r_t` 是策略逐 bar 净收益，`f_j` 是几个"用简单规则就能
复制"的风格收益（`style_factor_returns`）。β 显著 = 策略收益有一部分只是这种风格；剥离风格后的收益
`r_t − Σ β_j f_{j,t}`（= α + ε）的 Sharpe（`alpha_sharpe`）才是"选币能力"的估计。只对 BTC 回归（β≈0）只排除了
"押大盘方向"一种解释，低波动 / 规模 / 反转这些跟大盘方向无关的风格要一起放进去。

**分期稳定性**（`period_stats`）：按季度切开算净 Sharpe / 收益。一个真正的 alpha 应该在大多数季度都为正，而不是
靠一两个季度撑起来。

风格收益用跟策略同一个回测器（`score_backtest`）构造，时间标签口径一致：第 t 行 = t 时刻决策、持有期内实现的收益。
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from sherpa.metrics.performance import sharpe_ratio

from .score_backtest import cross_sectional_rank, run_score_backtest, target_path

STYLE_FACTORS = ("btc", "market", "low_vol", "small_size", "reversal", "momentum")


def style_factor_returns(
    close: pd.DataFrame,
    quote_volume: pd.DataFrame,
    mask: Optional[pd.DataFrame],
    *,
    interval: str,
    shift: int,
    benchmark_symbol: str,
    quantile: float = 0.2,
    rebalance_every: int = 6,
) -> pd.DataFrame:
    """几个简单风格的逐 bar 收益，index 跟 `run_score_backtest` 的结果对齐：

    - `btc`：大盘锚点自己的收益；
    - `market`：掩码内全部 symbol 等权的收益（山寨币整体）；
    - `low_vol`：做多近 42 根波动最低的 20%、做空最高的 20%；
    - `small_size`：做多近 42 根平均成交额最小的 20%、做空最大的 20%；
    - `reversal`：做多近 6 根（1 天）跌得最多的 20%、做空涨得最多的 20%；
    - `momentum`：做多近 120 根（20 天）涨得最多的 20%、做空跌得最多的 20%。

    多空组合都是掩码内、每 `rebalance_every` 根调仓、零成本、多空各 0.5（跟策略同一个 `target_path`）。
    """
    mask = close.notna() if mask is None else mask.reindex_like(close).fillna(False)
    returns = close.pct_change(fill_method=None)
    forward = returns.shift(-shift)  # 第 t 行 = close[t+shift-1] -> close[t+shift]，跟回测结果同一时间标签
    out = {
        "btc": forward[benchmark_symbol],
        "market": forward.where(mask).mean(axis=1),
    }
    raw_scores = {
        "low_vol": -returns.rolling(42).std(),
        "small_size": -quote_volume.rolling(42).mean(),
        "reversal": -close.pct_change(6, fill_method=None),
        "momentum": close.pct_change(120, fill_method=None),
    }
    spec = {"method": "top_quantile", "q": quantile, "exit_q": quantile}
    for name, raw in raw_scores.items():
        ranked = cross_sectional_rank(raw.where(np.isfinite(raw)).where(mask))
        gross, _ = run_score_backtest(
            target_path(ranked, spec, rebalance_every), close, interval, shift=shift, rebalance_every=rebalance_every
        )
        out[name] = gross
    frame = pd.DataFrame(out)
    return frame.iloc[:-shift] if shift > 0 else frame  # 最后 shift 行还没有实现的收益


def attribute(returns: pd.Series, factors: pd.DataFrame, *, periods_per_year: float) -> dict[str, Any]:
    """`returns ~ 截距 + factors` 的 OLS。返回：

    - `raw_sharpe`：原始 Sharpe；`alpha_sharpe`：剥离风格后（`returns − Σ β·f`）的 Sharpe；
    - `alpha_ann`：截距 × 每年 bar 数（年化 α）；`alpha_t`：截距的普通 OLS t 值（没做自相关修正，只作参考）；
    - `beta[<因子>]`：各风格暴露；`r2`：风格能解释的方差比例。

    只用两边都有值的 bar；样本少于 30 根返回 NaN。
    """
    data = pd.concat([returns.rename("_r"), factors], axis=1).dropna()
    names = list(factors.columns)
    nan = {"bars": len(data), "raw_sharpe": np.nan, "alpha_sharpe": np.nan, "alpha_ann": np.nan, "alpha_t": np.nan,
           "r2": np.nan, **{f"beta[{n}]": np.nan for n in names}}
    if len(data) < 30:
        return nan
    y = data["_r"].to_numpy()
    x = np.column_stack([np.ones(len(data)), data[names].to_numpy()])
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    resid = y - x @ coef
    dof = max(len(y) - x.shape[1], 1)
    sigma2 = float(resid @ resid) / dof
    try:
        se_alpha = float(np.sqrt(sigma2 * np.linalg.inv(x.T @ x)[0, 0]))
    except np.linalg.LinAlgError:
        se_alpha = np.nan
    total = float(((y - y.mean()) ** 2).sum())
    alpha_part = pd.Series(y - x[:, 1:] @ coef[1:], index=data.index)  # = 截距 + 残差
    return {
        "bars": len(data),
        "raw_sharpe": sharpe_ratio(data["_r"], periods_per_year=periods_per_year),
        "alpha_sharpe": sharpe_ratio(alpha_part, periods_per_year=periods_per_year),
        "alpha_ann": float(coef[0] * periods_per_year),
        "alpha_t": float(coef[0] / se_alpha) if se_alpha and np.isfinite(se_alpha) and se_alpha > 0 else np.nan,
        "r2": 1.0 - float(resid @ resid) / total if total > 0 else np.nan,
        **{f"beta[{n}]": float(c) for n, c in zip(names, coef[1:])},
    }


def period_stats(returns: pd.Series, *, periods_per_year: float, freq: str = "Q", min_bars: int = 60) -> pd.DataFrame:
    """按自然季度（`freq="Q"`）切开：每期的 bar 数、净 Sharpe、累计收益（简单加总）。

    不足 `min_bars` 根的期（比如模型从季末才开始、只覆盖了几根 bar）Sharpe 和收益记 NaN——几根 bar 算出来的
    年化 Sharpe 可以是 ±十几，没有意义。4h 周期一个季度约 540 根，默认门槛 60 根（10 天）。
    """
    if not isinstance(returns.index, pd.DatetimeIndex) or returns.empty:
        return pd.DataFrame(columns=["bars", "sharpe", "return"])
    index = returns.index.tz_localize(None) if returns.index.tz is not None else returns.index
    groups = returns.groupby(index.to_period(freq))
    stats = pd.DataFrame({
        "bars": groups.size(),
        "sharpe": groups.apply(lambda r: sharpe_ratio(r, periods_per_year=periods_per_year)),
        "return": groups.sum(),
    })
    stats.loc[stats["bars"] < min_bars, ["sharpe", "return"]] = np.nan
    return stats
