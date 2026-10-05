"""训练集构建和滚动时间表（纯函数，不连数据库，单测直接喂合成面板）。

训练集只含**损失掩码内、标签已知**的行，按时间、再按 symbol 排好序（同一期的行连续，`objective.py` 按期分组靠这个）。
特征和标签对整段面板一次算好，每个重训时点只按时间切片——特征第 t 行只用 `<= t` 的数据（`features.py` 的单测保证），
标签第 t 行用到 `close[t + delay + horizon]`，所以重训时点 τ 只能用 `t <= τ − (horizon + delay)` 根 bar 的行（purge）。
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Union

import numpy as np
import pandas as pd

from sherpa.alpha.custom.ml.features import FeatureSpec, build_features, cross_sectional_rank
from sherpa.alpha.liquidity import LiquidityFilter
from sherpa.backtest.style_exposure import default_style_exposures
from sherpa.data.schema import BarPanel, interval_to_timedelta
from sherpa.metrics.factor import forward_returns
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

from objective import period_starts, tail_weights


@dataclass
class TrainingFrame:
    """损失掩码内、标签已知的行（按时间排序）。"""

    features: np.ndarray  # (n, K) float32
    feature_names: list[str]
    y: np.ndarray  # 期内截面排名后的标签，[-0.5, 0.5]
    weights: np.ndarray  # 首尾加权
    label: np.ndarray  # 原始标签（未来收益；开了标签中性化时是残差收益），算 RankIC 报告用
    times: pd.DatetimeIndex
    symbols: np.ndarray

    def __len__(self) -> int:
        return len(self.y)

    def rows_between(self, start: Optional[pd.Timestamp], end: pd.Timestamp, *, end_inclusive: bool = True) -> slice:
        """时间在 [start, end]（或 [start, end)）内的行，行按时间排好序所以是一段连续切片。"""
        lo = 0 if start is None else int(self.times.searchsorted(start, side="left")) # searchsorted 返回的是索引号, left 表达第一个大于或者等于 start 的位置
        hi = int(self.times.searchsorted(end, side="right" if end_inclusive else "left")) # right 表示 第一个严格大于 end 的位置， 所以 end 是被包含的
        return slice(lo, hi)


def build_labels(
    panel: BarPanel,
    mask: Optional[pd.DataFrame],
    *,
    horizon: int,
    delay: int,
    neutralize_label: bool,
    benchmark_symbol: str,
) -> pd.DataFrame:
    """`(T, N)` 标签：研究配置口径的未来收益，套损失掩码；`neutralize_label` 时对 Beta / Size 截面回归取残差。"""
    labels = forward_returns(panel.close, horizon=horizon, delay=delay) # labels 是对齐 panel.close 的2D面板，(T, N)的未来收益标签，NaN表示不参与训练的行
    if mask is not None:
        labels = labels.where(mask) # 经过 mask 的正负网格（点亮成那些 存在窗口中位值 同时 超过流动性截面阈值 的那些标的）
    if neutralize_label:
        labels = neutralize(labels, default_style_exposures(panel, benchmark_symbol=benchmark_symbol))
    return labels


def liquidity_from_tradable(tradable: Union[bool, Mapping[str, Any]]) -> LiquidityFilter:
    """研究线 `track.json` 的 `preprocess.tradable_mask` 配置 -> 等价的 `LiquidityFilter`（补全 `tradable_mask` 的默认值）。

    训练脚本拿它跟模型的 `spec.liquidity` 比：模型训练 / 推断用的流动性范围，必须跟研究流水线评估时的外层掩码一致。
    `false`（不掩码）对应 `LiquidityFilter()`（不限制）。
    """
    if tradable is False:
        return LiquidityFilter()
    defaults = {
        name: param.default
        for name, param in inspect.signature(tradable_mask).parameters.items()
        if param.default is not inspect.Parameter.empty
    }
    overrides = {} if tradable is True else dict(tradable)
    return LiquidityFilter(**{**defaults, **overrides})


def build_training_frame(
    panel: BarPanel,
    spec: FeatureSpec,
    *,
    horizon: int,
    delay: int,
    neutralize_label: bool,
    tail_quantile: float,
    tail_weight: float,
) -> TrainingFrame:
    # 流动性范围（损失掩码）只有一个来源：spec.liquidity。特征的截面排名、标签都用这同一张 (T, N) 布尔表
    scope = spec.liquidity.mask(panel)
    features = build_features(panel, spec, scope)

    # labels 是对齐 close的 2d 面板，(T, N)的未来收益标签，NaN表示不参与训练的行
    labels = build_labels(
        panel, scope, horizon=horizon, delay=delay, neutralize_label=neutralize_label,
        benchmark_symbol=spec.benchmark_symbol,
    )
    label_rank = cross_sectional_rank(labels)  # 只在掩码内有值，所以就是损失掩码内的截面排名

    times = features.index.get_level_values("start_time")
    symbols = features.index.get_level_values("symbol")
    ti = panel.close.index.get_indexer(times)
    si = panel.close.columns.get_indexer(symbols)
    y = label_rank.to_numpy(dtype="float64")[ti, si]
    raw = labels.to_numpy(dtype="float64")[ti, si]
    keep = np.isfinite(y) & np.isfinite(raw)

    # 特征和标签靠"行号相同"对齐：y 是按 features.index 的顺序逐行查出来的，第 i 个 y 就是 features 第 i 行那个
    # (时间, 币) 的标签。to_numpy() 只去掉 MultiIndex，行列都不变（二维，不是压成一条）；keep 按行筛，两边用同一个 keep。
    #
    # ① 用坐标从 label_rank 里查 y。label_rank 跟 panel.close 同一张 (T, N) 网格（行号 / 列号标在边上）。
    #    例子：2 根 bar × 3 个币，08:00 SOL 没有收盘价（停牌 / 缺数据），其余格子都有收盘价：
    #
    #   close 有没有值        BTC(0)  ETH(1)  SOL(2)          label_rank            BTC(0)  ETH(1)  SOL(2)
    #   04:00 (0)               有      有      有             04:00 (0)              0.5     NaN     0.0   ← ETH 有价但不在掩码内（流动性不够）
    #   08:00 (1)               有      有      无             08:00 (1)              0.5     0.0     NaN   ← SOL 没价，标签也是 NaN
    #
    #   features 的行 = close 有值的格子（按时间、再按币的顺序），共 5 行；08:00 SOL 没价，features 里根本没有这一行：
    #     (04:00, BTC) (04:00, ETH) (04:00, SOL) (08:00, BTC) (08:00, ETH)
    #   ti = close.index.get_indexer(时间)   = [0, 0, 0, 1, 1]
    #   si = close.columns.get_indexer(币)   = [0, 1, 2, 0, 1]
    #   A  = label_rank.to_numpy()           仍是二维 (T, N) = (2, 3)
    #   y  = A[ti, si]                       = [A[0,0], A[0,1], A[0,2], A[1,0], A[1,1]] = [0.5, NaN, 0.0, 0.5, 0.0]
    #        两个等长的整数数组做下标 = n 对 (行, 列) 坐标逐对取值，结果是长度 n 的一维数组，顺序跟 features 的行一致
    #
    # ② 特征矩阵、标签、keep 并排（第 i 行 ↔ 第 i 个）：
    #
    #   features（两列，ret 和vol）     features.to_numpy()      y        keep
    #   (04:00, BTC)  ret_1=0.00 vol=0.1  →  [0.00, 0.1]       0.5      True
    #   (04:00, ETH)  ret_1=NaN  vol=0.2  →  [ NaN, 0.2]       NaN      False   ← 掩码外（特征是 NaN 不影响，看的是标签）
    #   (04:00, SOL)  ret_1=0.50 vol=0.3  →  [0.50, 0.3]       0.0      True
    #   (08:00, BTC)  ret_1=0.17 vol=0.4  →  [0.17, 0.4]       0.5      True
    #   (08:00, ETH)  ret_1=0.50 vol=0.5  →  [0.50, 0.5]       0.0      True
    #                                       形状 (n, K)=(5, 2)  (5,)     (5,)
    #
    #   features[keep] = [[0.00, 0.1], [0.50, 0.3], [0.17, 0.4], [0.50, 0.5]]   形状 (m, K)=(4, 2)：整行留下 / 去掉
    #   y[keep]        = [0.5, 0.0, 0.5, 0.0]                                    形状 (m,)=(4,)
    #   times[keep] / symbols[keep] 记着每一行是哪个 (时间, 币)，后面按时间切重训时点、按期分组算 IC 都靠它。
    return TrainingFrame(
        features=features.to_numpy(dtype="float32")[keep],
        feature_names=list(features.columns),
        y=y[keep],
        weights=tail_weights(y[keep], tail_quantile=tail_quantile, tail_weight=tail_weight),
        label=raw[keep],
        times=pd.DatetimeIndex(times[keep]),
        symbols=np.asarray(symbols[keep]),
    )


@dataclass(frozen=True)
class Fold:
    """一个重训时点：模型服务 [valid_from, valid_until)，训练只用 `train_until` 及以前的行。"""

    valid_from: pd.Timestamp
    valid_until: pd.Timestamp
    train_from: Optional[pd.Timestamp]
    train_until: pd.Timestamp


def plan_folds(
    *,
    research_start: pd.Timestamp,
    last_bar: pd.Timestamp,
    interval: str,
    retrain_every_bars: int,
    min_train_bars: int,
    purge_bars: int,
    train_window_bars: Optional[int] = None,
) -> list[Fold]:
    """重训时点 τ_k = research_start + (min_train_bars + k·retrain_every_bars) 根 bar，直到 `last_bar`。

    时间表只由研究起点和参数决定，跟面板取到哪天无关：以后数据变长、再跑一次训练，前面的重训时点不变，已经训练好的
    模型可以直接复用，只追加新的。

    返回一个含有多个fold的列表，每个时点是一个 Fold， Fold（以第 38 个为例）
        valid_from  = 2024-07-09 00:00   这个模型从这里开始负责打分
        valid_until = 2024-07-29 00:00   负责到这里（不含）
        train_from  = None               扩展窗口：从数据起点开始用
        train_until = 2024-07-08 16:00   训练行截止 = valid_from − 2 根 bar（purge）
    """
    bar = interval_to_timedelta(interval)
    folds = []
    k = 0
    while True:
        tau = research_start + (min_train_bars + k * retrain_every_bars) * bar
        if tau > last_bar:
            break
        folds.append(Fold(
            valid_from=tau,
            valid_until=tau + retrain_every_bars * bar,
            train_from=None if train_window_bars is None else tau - train_window_bars * bar,
            train_until=tau - purge_bars * bar,
        ))
        k += 1
    return folds


def split_inner_validation(
    frame: TrainingFrame, rows: slice, *, train_until: pd.Timestamp, valid_bars: int, purge_bars: int, interval: str
) -> tuple[slice, slice]:
    """训练窗口 -> (拟合段, 内部验证段)，用于第一步早停。

    验证段固定是窗口里最近的 `valid_bars` 根 bar：时间在 (train_until − valid_bars 根, train_until]；拟合段是它之前、
    再隔开 `purge_bars` 根 bar 的部分（拟合段最后一行的标签用到 t + purge 根的收盘价，不能伸进验证段）。

        训练窗口 rows：  [────────── 拟合段 fit ──────────]  purge  [──── 验证段 valid（最近 valid_bars 根）────]
                                                                                                       train_until
    """
    bar = interval_to_timedelta(interval)
    first_valid = train_until - (valid_bars - 1) * bar
    valid = slice(max(rows.start, int(frame.times.searchsorted(first_valid, side="left"))), rows.stop)
    fit = slice(rows.start, max(rows.start, int(frame.times.searchsorted(first_valid - purge_bars * bar, side="left"))))
    for name, part in (("拟合段", fit), ("验证段", valid)):
        periods = len(period_starts(frame.times[part].to_numpy()))
        if periods < 10:
            raise ValueError(f"{name}只有 {periods} 期，太少（训练窗口不够长，或者 valid_bars 太大）")
    return fit, valid
