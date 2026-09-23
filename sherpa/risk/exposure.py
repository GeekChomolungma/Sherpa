"""风险暴露矩阵：截面中性化回归要用的自变量。

跟 `sherpa.metrics` 同一条包级约定（见 `sherpa/risk/__init__.py`）：只依赖 pandas/numpy，
不 import 仓库内其他模块（哪怕是同样只依赖 pandas/numpy 的 `sherpa.alpha.ops`）——保持
`sherpa.risk` 能完全脱离 Sherpa 其余部分单独复用/测试，边界处理方式跟
`sherpa.metrics.regime` 对 `sherpa.alpha.ops` 的态度一致：需要的滚动算子直接用 pandas
写一遍，不引入新的依赖方向。
"""

from __future__ import annotations

import pandas as pd

DEFAULT_BETA_WINDOW = 120  # ~120 根k线的滚动窗口


def _broadcast(series: pd.Series, columns) -> pd.DataFrame:
    """把一条时序 Series 复制成跟 `columns` 对齐的 (T, N) 常量列 DataFrame。"""
    return pd.DataFrame({column: series for column in columns}, index=series.index)


def rolling_beta(
    close: pd.DataFrame,
    *,
    benchmark_symbol: str,
    window: int = DEFAULT_BETA_WINDOW,
) -> pd.DataFrame:
    """逐 symbol 对 `benchmark_symbol`（通常是 BTCUSDT）的滚动 beta 暴露：

    `Cov(ret_i, ret_benchmark) / Var(ret_benchmark)`，窗口内滚动计算，输出跟 `close` 同
    形状的 `(T, N)` 矩阵。

    自变量必须是"每个 symbol 自己对大盘的敏感度"，不能直接用"大盘本身涨跌了多少"——后者
    在同一个截面里对所有 symbol 都是同一个数，作为截面回归的自变量方差恒为 0，回归无解
    （完全共线）。这里产出的才是货真价实随 symbol/时刻同时变化的截面特征，可以直接喂给
    `neutralize()` 当一个 exposure。

    只用 `<= t` 的滚动窗口，不引入前视泄露；滚动窗口还没攒够数据的 warm-up 期一律是 NaN。
    """
    if benchmark_symbol not in close.columns:
        raise KeyError(f"benchmark_symbol {benchmark_symbol!r} 不在 close.columns 里，无法计算滚动 beta")

    returns = close.pct_change()
    benchmark_returns = returns[benchmark_symbol]
    benchmark_broadcast = _broadcast(benchmark_returns, close.columns)

    covariance = returns.rolling(window).cov(benchmark_broadcast)
    variance = benchmark_returns.rolling(window).var()

    beta = covariance.div(variance, axis=0)

    # 窗口内基准收益率方差趋近于 0（比如极端地量的冷启动期）时，除法在数值上不稳定，会
    # 产出没有意义的巨大 beta 值而不是诚实的 NaN——用一个极小阈值收口，跟
    # `sherpa.alpha.ops.ts_corr` 处理同一类数值坑用的是同一种策略。
    variance_broadcast = _broadcast(variance, close.columns)
    return beta.where(variance_broadcast.abs() > 1e-12)
