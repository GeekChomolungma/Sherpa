"""机器学习 alpha 的特征构建：`BarPanel` -> `(T, N, K)` 特征面板（长表）。**训练和推断共用这一份实现**。

训练（`research/ml_training/`）和推断（`MLAlpha.compute()`）如果各写一份特征，线上和回测会悄悄对不上——
同设计文档 §8.3 决策1：会改变决策结果的逻辑不允许写两份。设计见同目录上一级的 `ML_ALPHA_DESIGN.md` §2.2。

三组特征：

- **A. 原始字段衍生**（`SYMBOL_FEATURES`）：多窗口收益、波动、振幅、成交额、主动买入占比、单笔成交额、离高低点距离、
  对大盘的 Beta、OI 变化。每期**截面排名**（平移到 [-0.5, 0.5]）；
- **B. 现有 alpha 分值**（`FeatureSpec.alphas`）：按 registry 的 qualified_name 计算原始分数，同样每期截面排名；
- **C. 市场状态变量**（`MARKET_FEATURES`）：`sherpa.metrics.regime` 里的连续量（广度、波动率分位数……），同一期所有
  symbol 取值相同，不做截面处理。它们单独改变不了截面排序，只能通过和 A/B 的交互起作用（设计文档 §5.2）。

两条硬规矩（都有单测）：

1. **point-in-time**：第 t 行只用 `<= t` 的数据。所有时序运算都是 rolling / pct_change，截面运算只看当期；
2. **截面统计量只在当期有数据的 symbol 上算**：还没上线 / 已下架的列整列是 NaN，`rank(axis=1)` 会跳过 NaN。
   面板里多几列全 NaN 的币，结果不变（研究流水线各阶段的 universe 截止时间不同，靠的就是这一点）。
3. **A、B 组的截面排名只在流动性范围内做**（`FeatureSpec.liquidity`）：时序部分先在全量数据上算完，再把范围外的格子
   盖成 NaN（`sherpa.alpha.liquidity.restrict`），最后排名。顺序不能反——范围逐期变化，先盖掉再 rolling，在范围边缘
   进进出出的币时序会被打断，大段特征变成 NaN。训练（标签掩码）和推断都用同一个 `spec.liquidity`，口径不会分叉。

截面排名不做 rank-gauss：第一版模型是树模型，对单调变换不敏感；以后换神经网络再加。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Callable, Iterator, Optional

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel
from sherpa.metrics.regime import (
    DEFAULT_LOOKBACK as REGIME_LOOKBACK,
    compute_dispersion_regime,
    compute_liquidity_regime,
    compute_trend_regime,
    compute_volatility_regime,
)
from sherpa.risk.exposure import DEFAULT_BETA_WINDOW, rolling_beta

from ...base import registry
from ...liquidity import LiquidityFilter, restrict

FEATURE_INDEX_NAMES = ("start_time", "symbol")


def cross_sectional_rank(x: pd.DataFrame) -> pd.DataFrame:
    """每期截面百分位排名，平移到 [-0.5, 0.5]。±inf 也当成缺失NaN；所有NaN（没上线 / 已下架 / 值无穷）不参与排名。"""
    return x.where(np.isfinite(x)).rank(axis=1, pct=True) - 0.5


def _safe_div(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    return a / b.where(b != 0)


# ---- A. 原始字段衍生：(名字, panel -> (T, N) 原始值)，截面排名在外面统一做 ----

def _oi_change(periods: int) -> Callable[[BarPanel], pd.DataFrame]:
    def compute(panel: BarPanel) -> pd.DataFrame:
        if panel.open_interest is None:  # 没取 OI（或 1m 周期）时整列缺失，LightGBM 能处理 NaN
            return pd.DataFrame(np.nan, index=panel.index, columns=panel.close.columns)
        return panel.open_interest.pct_change(periods, fill_method=None)

    return compute


# 窗口单位是 bar（研究周期 4h）：1 根 = 4 小时，6 根 = 1 天，42 根 = 7 天，120 根 = 20 天。每个特征只给原始值，
# 每期截面排名在 `_symbol_features` 里统一做，模型看到的是"这个币在当期所有币里排第几"。
#
# 2026-10-02 按真实数据的截面相关去冗余：range_6 跟 vol_42 相关 +0.81、trade_size_42 跟 quote_volume_42 相关 +0.76，
# 各去掉一个；ret_42 去掉。
SYMBOL_FEATURES: tuple[tuple[str, Callable[[BarPanel], pd.DataFrame]], ...] = (
    # ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    # │ 1. 过去收益：t−k → t 已经发生的涨跌（标签是 t+1 → t+2，两者不重叠）                            │
    # │    ret_1    (close_t − close_{t−1}) / close_{t−1}，最近 4 小时。短期反转：刚拉升的币下一根常回吐  │
    # │    ret_6    (close_t − close_{t−6}) / close_{t−6}，最近 1 天。日内级别的反转 / 延续              │
    # │    ret_120  (close_t − close_{t−120}) / close_{t−120}，最近 20 天。中期动量                      │
    # └──────────────────────────────────────────────────────────────────────────────────────────────┘
    ("ret_1", lambda p: p.close.pct_change(1, fill_method=None)),
    ("ret_6", lambda p: p.close.pct_change(6, fill_method=None)),
    ("ret_120", lambda p: p.close.pct_change(120, fill_method=None)),
    # ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    # │ 2. 波动：这个币近期动得有多猛                                                                  │
    # │    vol_42  近 7 天逐根收益的标准差。注意：第一版模型最依赖它（打分跟它的截面秩相关约 −0.6），       │
    # │            学到的是"高波动币中位收益低"，赚不到平均收益，见 research/ml_training/README.md 最后一节 │
    # └──────────────────────────────────────────────────────────────────────────────────────────────┘
    ("vol_42", lambda p: p.close.pct_change(fill_method=None).rolling(42).std()),
    # ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    # │ 3. 价格在近期区间里的位置                                                                      │
    # │    dist_high_42  close / 7 天最高价 − 1，<= 0，越接近 0 越靠近高点：突破 / 高位回落              │
    # │    dist_low_42   close / 7 天最低价 − 1，>= 0，越接近 0 越靠近低点：超跌 / 底部反弹              │
    # │    两者彼此几乎不相关（+0.08），但都跟 vol_42 有约 0.5 的结构性相关（波动大的币离高低点都远）      │
    # └──────────────────────────────────────────────────────────────────────────────────────────────┘
    ("dist_high_42", lambda p: _safe_div(p.close, p.high.rolling(42).max()) - 1),
    ("dist_low_42", lambda p: _safe_div(p.close, p.low.rolling(42).min()) - 1),
    # ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    # │ 4. 成交规模与放量                                                                              │
    # │    quote_volume_42          近 7 天平均成交额（USDT）：活跃度 / 规模，跟中性化剥离的 Size 同类   │
    # │    quote_volume_surge_6_42  近 1 天平均成交额 / 近 7 天平均成交额，> 1 = 放量：突然有资金关注     │
    # └──────────────────────────────────────────────────────────────────────────────────────────────┘
    ("quote_volume_42", lambda p: p.quote_volume.rolling(42).mean()),
    ("quote_volume_surge_6_42", lambda p: _safe_div(p.quote_volume.rolling(6).mean(), p.quote_volume.rolling(42).mean())),
    # ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    # │ 5. 主动买卖：资金流向                                                                          │
    # │    taker_buy_ratio_6  近 1 天主动买入成交额 / 总成交额，> 0.5 = 买盘更主动                       │
    # └──────────────────────────────────────────────────────────────────────────────────────────────┘
    ("taker_buy_ratio_6", lambda p: _safe_div(p.taker_buy_quote_volume.rolling(6).sum(), p.quote_volume.rolling(6).sum())),
    # ┌──────────────────────────────────────────────────────────────────────────────────────────────┐
    # │ 6. 持仓量（永续合约特有）：新资金在建仓还是离场                                                 │
    # │    oi_change_6   近 1 天未平仓量的变化率                                                        │
    # │    oi_change_42  近 7 天未平仓量的变化率                                                        │
    # │    面板没取 OI（或 1m 周期）时整列 NaN                                                          │
    # └──────────────────────────────────────────────────────────────────────────────────────────────┘
    ("oi_change_6", _oi_change(6)),
    ("oi_change_42", _oi_change(42)),
)
# ┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
# │ 7. 大盘联动（不在上面的元组里：要用大盘锚点，在 `_symbol_features` 里单独算，名字固定排在 A 组最后）   │
# │    beta  近 120 根逐根收益对 BTC 的回归系数，> 1 = 比 BTC 动得更猛。可以跟 C 组市场状态交互，           │
# │          比如"牛市偏好高 Beta"                                                                     │
# └──────────────────────────────────────────────────────────────────────────────────────────────────┘
BETA_FEATURE = "beta"
SYMBOL_FEATURE_LOOKBACK = max(121, DEFAULT_BETA_WINDOW + 1)

# ---- C. 市场状态变量：只用本身就是比例 / 滚动分位数、跨年份可比的量 ----

MARKET_FEATURES: tuple[str, ...] = (
    "market_breadth",
    "benchmark_trend_up",
    "benchmark_ma_gap",
    "benchmark_ret_42",
    "rv_quantile",
    "dispersion_quantile",
    "volume_quantile",
    "market_taker_buy_ratio",
)
# volatility 维度：窗口 120 的已实现波动，再取 120 根的滚动分位数，最长回看 240 根。
MARKET_FEATURE_LOOKBACK = 2 * REGIME_LOOKBACK


@dataclass(frozen=True)
class FeatureSpec:
    """一个模型用的特征清单。训练时写进模型清单（`fingerprint`），推断时校验一致——特征变了，旧模型就不能用。

    `alphas` 是 B 组要用的已注册 alpha（qualified_name），调用方负责先 import 它们所在的模块。

    `liquidity` 是这个模型的流动性范围（门槛参数同 `tradable_mask`），三处共用这一份：
    - A、B 组特征的截面排名只在范围内做（`build_features`）；
    - 训练时标签和损失只用范围内的行（`research/ml_training/dataset.build_training_frame`）；
    - 推断时范围外的格子不打分（`MLAlpha.compute`）。
    研究流水线评估用的外层掩码（研究线 `track.json` 的 `tradable_mask`）必须跟它一致，训练脚本开头会校验。
    默认 `LiquidityFilter()` = 不限制（当期有收盘价的全部 symbol）。
    """

    name: str
    version: int
    alphas: tuple[str, ...] = ()
    benchmark_symbol: str = "BTCUSDT"
    liquidity: LiquidityFilter = LiquidityFilter()

    @property
    def feature_names(self) -> tuple[str, ...]:
        symbol = tuple(name for name, _ in SYMBOL_FEATURES) + (BETA_FEATURE,)
        alphas = tuple(f"alpha:{name}" for name in self.alphas)
        market = tuple(f"market:{name}" for name in MARKET_FEATURES)
        return symbol + alphas + market

    @property
    def fingerprint(self) -> str:
        payload = {
            "name": self.name,
            "version": self.version,
            "benchmark_symbol": self.benchmark_symbol,
            "features": list(self.feature_names),
            "liquidity": asdict(self.liquidity),
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]

    @property
    def min_lookback(self) -> int:
        alpha_lookback = max((registry.get(name).min_lookback for name in self.alphas), default=1)
        return max(SYMBOL_FEATURE_LOOKBACK, MARKET_FEATURE_LOOKBACK, alpha_lookback, self.liquidity.min_lookback)


def _symbol_features(panel: BarPanel, spec: FeatureSpec, scope: pd.DataFrame) -> Iterator[tuple[str, pd.DataFrame]]:
    """A、B 组：① 在全量数据上算原始值（时序不被范围打断）→ ② `restrict` 盖掉范围外 → ③ 只在范围内截面排名。"""

    def ranked(raw: pd.DataFrame) -> pd.DataFrame:
        return cross_sectional_rank(restrict(raw, scope))

    for name, compute in SYMBOL_FEATURES:
        yield name, ranked(compute(panel))
    yield BETA_FEATURE, ranked(rolling_beta(panel.close, benchmark_symbol=spec.benchmark_symbol))
    for name in spec.alphas:
        yield f"alpha:{name}", ranked(registry.get(name)().compute(panel))


def market_features(panel: BarPanel, spec: FeatureSpec) -> pd.DataFrame:
    """C 组：`(T, 8)`，行 = bar。参数全部用 `sherpa.metrics.regime` 的默认值，跟研究流水线的 regime 打标同一口径。"""
    close = panel.close
    trend = compute_trend_regime(close, benchmark_symbol=spec.benchmark_symbol)
    volatility = compute_volatility_regime(close)
    dispersion = compute_dispersion_regime(close)
    liquidity = compute_liquidity_regime(panel.quote_volume, panel.taker_buy_quote_volume)
    benchmark = close[spec.benchmark_symbol]
    benchmark_ma = benchmark.rolling(REGIME_LOOKBACK).mean()
    frame = pd.DataFrame(
        {
            "market_breadth": trend["market_breadth"],
            "benchmark_trend_up": trend["benchmark_trend_up"].astype("float64"),
            "benchmark_ma_gap": benchmark / benchmark_ma - 1,
            "benchmark_ret_42": benchmark.pct_change(42, fill_method=None),
            "rv_quantile": volatility["rv_quantile"],
            "dispersion_quantile": dispersion["dispersion_quantile"],
            "volume_quantile": liquidity["volume_quantile"],
            "market_taker_buy_ratio": liquidity["taker_buy_ratio"],
        },
        index=close.index,
    )
    return frame[list(MARKET_FEATURES)]


def build_features(panel: BarPanel, spec: FeatureSpec, scope: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """特征长表：行 = 当期有收盘价的 (start_time, symbol)，按时间、再按 symbol 排好序；列 = `spec.feature_names`，float32。

    长表而不是三维数组：币种上市 / 下架很多，`(T, N)` 里大半是空的；长表也能直接喂给 LightGBM。

    `scope` 是 `spec.liquidity.mask(panel)`；调用方已经算过（训练要拿它盖标签、推断要拿它挑行）就传进来，省一次计算。
    范围外的行照样在长表里，A、B 组特征是 NaN、C 组照常有值。
    """
    if scope is None:
        scope = spec.liquidity.mask(panel)
    close = panel.close
    present = close.notna().to_numpy()
    rows, cols = np.nonzero(present)  # 行优先：先按时间、再按 symbol 的列顺序
    # rows 和 cols 示例
    # rows（时间）：['00:00', '00:00', '04:00', '04:00', '04:00', ...]
    # cols（币种）：['BTC', 'SOL', 'BTC', 'ETH', 'SOL', ...]

    index = pd.MultiIndex.from_arrays([close.index[rows], close.columns[cols]], names=FEATURE_INDEX_NAMES)
    # index 示例
    # MultiIndex([
    #     ('00:00', 'BTC'),
    #     ('00:00', 'SOL'),  # 注意：这里没有 ('00:00', 'ETH')，因为 ETH 当时是 NaN 被过滤了！
    #     ('04:00', 'BTC'),
    #     ('04:00', 'ETH'),
    #     ('04:00', 'SOL'),
    #     ('08:00', 'BTC'),
    #     ('08:00', 'ETH'),
    #     ('08:00', 'SOL'),
    #     ('12:00', 'BTC'),
    #     ('12:00', 'ETH'),
    #     ('12:00', 'SOL')
    # ], names=['start_time', 'symbol'])

    # pick 处理示例
    # 将(T, N) 的原始值 frame 对齐到 index=close.index, columns=close.columns成新的dataframe, 
    # 再把dataframe换成(T*N,)的一维数组, 再按rows, cols取出当期有收盘价的 (start_time, symbol) 的值，NaN保持NaN
    def pick(frame: pd.DataFrame) -> np.ndarray:
        values = frame.reindex(index=close.index, columns=close.columns).to_numpy(dtype="float64")[rows, cols]
        return np.where(np.isfinite(values), values, np.nan).astype("float32")

    # _symbol_features输出示例
    # name = 'ret_1', 
    # frame = rank[restrict(p.close.pct_change(1, fill_method=None), scope)] 对齐 原始的barPanel.close, 形状也是（T, N)
    data: dict[str, np.ndarray] = {name: pick(frame) for name, frame in _symbol_features(panel, spec, scope)}
    # 最终data示例
    # {
    #    'ret_1': array([-0.0005,  0.0012, -0.0003,  0.0008,  0.0015, ...], dtype=float32),  # 虽然是纯粹值，但其实是跟rows, cols一一对应，NaN保持NaN
    #     ...
    #    'beta': array([ 0.85,  0.92,  0.88,  0.90,  0.95, ...], dtype=float32),
    #    'alpha:my_alpha': array([-0.0002,  0.0005, -0.0001,  0.0003,  0.0007, ...], dtype=float32),
    #     ...
    # }  

    market = market_features(panel, spec).to_numpy(dtype="float64")[rows]
    for i, name in enumerate(MARKET_FEATURES):
        column = market[:, i]
        data[f"market:{name}"] = np.where(np.isfinite(column), column, np.nan).astype("float32")

    features = pd.DataFrame(data, index=index) # 从data字典表，转换回到长表形式（真正的金融panel），index是MultiIndex(start_time, symbol), columns是spec.feature_names
    return features[list(spec.feature_names)]
