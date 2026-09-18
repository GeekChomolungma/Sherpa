"""市场状态（Regime）打标：`research/REGIME_FRAMEWORK_GUIDE.md` 的代码落地。

跟 `sherpa.metrics.factor` 一样只吃 pandas 对象，不认识 `BarPanel`/ClickHouse——`sherpa.metrics`
包级约定是"只依赖 pandas/numpy，不 import 仓库内其他模块"（见 `sherpa/metrics/__init__.py`），
`BarPanel` 拆包这一步交给调用方（`sherpa.backtest.regime_screening`）做，这里保持可以脱离数据层
单独复用/测试。

全部用 `.rolling()` 算滚动分位数，天然只用得到 <= 当前时刻的历史，满足 `REGIME_FRAMEWORK_GUIDE.md`
§4 的 Point-in-time 因果律红线，不需要额外做前视校验。滚动窗口还没攒够数据的 warm-up 阶段，
状态一律是 `pd.NA`，不能把"没数据"悄悄当成"normal"——那是在编造不存在的历史。

TODO（暂不实现，先记录设计意图）：滚动分位数 + 绝对下限兜底的混合判定。
当前 `compute_volatility_regime`/`compute_dispersion_regime`/`compute_liquidity_regime` 三个
维度都是纯相对阈值——只要在滚动窗口内相对最高就会被打成 "high"，哪怕整个窗口本身处于历史
级的极端平静期（比如一段长期地量成交后偶尔一次正常放量，也会被打成 "high liquidity"）。
业内更成熟的做法是"滚动分位数达标 **且** 绝对值本身也过了某个有经济意义的门槛"两个条件都
满足才判定为对应状态；但加密市场基础体量在几年内发生数量级变化（参见 `REGIME_FRAMEWORK_GUIDE.md`
§2），绝对门槛不能一劳永逸写死，大概率也需要跟着大周期分段重新标定。具体门槛怎么定、多久
重标一次，留到接上真实数据观察分布之后再定——现在不引入，不凭空拍一个不知道对不对的绝对值。
"""

from __future__ import annotations

import pandas as pd

DEFAULT_LOOKBACK = 30 # ~30 天 @ 1d bar 的滚动分位数观察窗口


def _quantile_bucket(
    rank: pd.Series,
    *,
    high_quantile: float | None,
    low_quantile: float | None,
    high_label: str,
    low_label: str,
    mid_label: str,
) -> pd.Series:
    """把一个 0~1 的滚动分位数序列切成三档；`rank` 为 NaN（warm-up 不足）的位置保持 `pd.NA`。"""
    state = pd.Series(pd.NA, index=rank.index, dtype="object")
    known = rank.notna()
    state[known] = mid_label
    if high_quantile is not None:
        state[known & (rank > high_quantile)] = high_label
    if low_quantile is not None:
        state[known & (rank < low_quantile)] = low_label
    return state


def compute_trend_regime(
    close: pd.DataFrame,
    *,
    benchmark_symbol: str,
    ma_period: int = 30,
    bull_breadth: float = 0.65,
    bear_breadth: float = 0.35,
) -> pd.DataFrame:
    """趋势与方向：大盘锚点动量 + 全市场广度联合判定（`REGIME_FRAMEWORK_GUIDE.md` §3.1）。

    `benchmark_symbol` 必须在 `close.columns` 里——趋势判定离不开一个大盘锚点（加密市场里
    通常是 BTC），没有就没法算，宁可显式报错也不要偷偷退化成"只看广度"的残缺逻辑。
    """
    if benchmark_symbol not in close.columns:
        raise KeyError(f"benchmark_symbol {benchmark_symbol!r} 不在 close.columns 里，无法计算趋势 regime")

    benchmark_close = close[benchmark_symbol]
    benchmark_ma = benchmark_close.rolling(ma_period).mean()
    known = benchmark_ma.notna()

    trend_up = benchmark_close > benchmark_ma  # warm-up 期间 ma 是 NaN，比较结果恒为 False，稍后被 known 掩掉
    breadth = (close.pct_change() > 0.0).mean(axis=1)

    is_bull = known & trend_up & (breadth > bull_breadth)
    is_bear = known & (~trend_up) & (breadth < bear_breadth)

    state = pd.Series(pd.NA, index=close.index, dtype="object")
    state[known] = "neutral"
    state[is_bull] = "bull"
    state[is_bear] = "bear"

    return pd.DataFrame(
        {
            "trend_state": state,
            "market_breadth": breadth,
            "benchmark_trend_up": trend_up.where(known),
        },
        index=close.index,
    )


def compute_volatility_regime(
    close: pd.DataFrame,
    *,
    window: int = 24,
    lookback: int = DEFAULT_LOOKBACK,
    high_quantile: float = 0.75,
    low_quantile: float = 0.25,
) -> pd.DataFrame:
    """波动率环境：全市场已实现波动率的滚动历史分位数（`REGIME_FRAMEWORK_GUIDE.md` §3.2）。"""
    returns = close.pct_change()
    market_rv = returns.rolling(window).std().mean(axis=1)
    rv_rank = market_rv.rolling(lookback).rank(pct=True)

    state = _quantile_bucket(
        rv_rank, high_quantile=high_quantile, low_quantile=low_quantile,
        high_label="high", low_label="low", mid_label="normal",
    )
    return pd.DataFrame({"volatility_state": state, "market_rv": market_rv, "rv_quantile": rv_rank}, index=close.index)


def compute_dispersion_regime(
    close: pd.DataFrame,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    high_quantile: float = 0.70,
    low_quantile: float = 0.30,
) -> pd.DataFrame:
    """离散度与相关性：截面收益标准差的滚动历史分位数（`REGIME_FRAMEWORK_GUIDE.md` §3.3）。"""
    returns = close.pct_change()
    dispersion = returns.std(axis=1)
    disp_rank = dispersion.rolling(lookback).rank(pct=True)

    state = _quantile_bucket(
        disp_rank, high_quantile=high_quantile, low_quantile=low_quantile,
        high_label="high", low_label="low", mid_label="normal",
    )
    return pd.DataFrame(
        {"dispersion_state": state, "dispersion": dispersion, "dispersion_quantile": disp_rank}, index=close.index
    )


def compute_liquidity_regime(
    quote_volume: pd.DataFrame,
    taker_buy_quote_volume: pd.DataFrame,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    high_quantile: float = 0.75,
    low_quantile: float = 0.25,
) -> pd.DataFrame:
    """流动性与活跃度：全市场截面总成交额的滚动历史分位数（`REGIME_FRAMEWORK_GUIDE.md` §3.4）。"""
    total_quote_volume = quote_volume.sum(axis=1)
    volume_rank = total_quote_volume.rolling(lookback).rank(pct=True)
    taker_buy_ratio = taker_buy_quote_volume.sum(axis=1) / total_quote_volume

    state = _quantile_bucket(
        volume_rank, high_quantile=high_quantile, low_quantile=low_quantile,
        high_label="high", low_label="starved", mid_label="normal",
    )
    return pd.DataFrame(
        {
            "liquidity_state": state,
            "total_quote_volume": total_quote_volume,
            "volume_quantile": volume_rank,
            "taker_buy_ratio": taker_buy_ratio,
        },
        index=quote_volume.index,
    )


def build_regime_report(
    close: pd.DataFrame,
    quote_volume: pd.DataFrame,
    taker_buy_quote_volume: pd.DataFrame,
    *,
    benchmark_symbol: str,
    ma_period: int = 30,
    vol_window: int = 24,
    lookback: int = DEFAULT_LOOKBACK,
) -> pd.DataFrame:
    """四维度联合打标矩阵：行=时间，列=trend/volatility/dispersion/liquidity 四个维度状态，
    外加一个 `regime_label` 结论列（四个状态原样拼接；任一维度还在 warm-up 期则整行为 NA）。

    `regime_label` 目前不做任何归并——四个维度各 2~3 档，组合起来有几十种，这里如实全部
    暴露；哪些组合可以合并成一档，要等接上具体 alpha 的条件 IC 表现后再决定，现在合并没有
    数据支撑，纯属主观拍脑袋（对应跟用户确认过的做法：先穷举，落地 alpha 体检时再归并）。
    """
    trend = compute_trend_regime(close, benchmark_symbol=benchmark_symbol, ma_period=ma_period)
    volatility = compute_volatility_regime(close, window=vol_window, lookback=lookback)
    dispersion = compute_dispersion_regime(close, lookback=lookback)
    liquidity = compute_liquidity_regime(quote_volume, taker_buy_quote_volume, lookback=lookback)

    dims = pd.DataFrame(
        {
            "trend": trend["trend_state"],
            "volatility": volatility["volatility_state"],
            "dispersion": dispersion["dispersion_state"],
            "liquidity": liquidity["liquidity_state"],
        },
        index=close.index,
    )

    complete = dims.notna().all(axis=1)
    joined = (
        dims["trend"].astype(str)
        + "|" + dims["volatility"].astype(str)
        + "|" + dims["dispersion"].astype(str)
        + "|" + dims["liquidity"].astype(str)
    )

    report = dims.copy()
    report["regime_label"] = joined.where(complete)
    return report
