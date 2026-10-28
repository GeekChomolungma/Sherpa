"""从 `RunSeries` 的底层逐期序列派生画图用的指标。全部是纯函数，窗口按"天"给、按数据的 bar 间隔换算成根数。

多模型比较时先把每个模型的底层序列裁到共同区间，再派生累计类指标（累计 RankIC、净值、回撤），保证各条线从同一个起点出发。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
import pandas as pd

from series import Combo, RunSeries


def bars_per_day(index: pd.DatetimeIndex) -> float:
    step = pd.Series(index).diff().median()
    return pd.Timedelta(days=1) / step if pd.notna(step) and step > pd.Timedelta(0) else 1.0


def rolling_mean(s: pd.Series, days: float) -> pd.Series:
    window = max(1, int(round(days * bars_per_day(s.index))))
    return s.rolling(window, min_periods=max(1, window // 2)).mean()


def cumulative(s: pd.Series) -> pd.Series:
    """缺失当 0 累加（某一期币太少、算不出 IC 时不贡献）。"""
    return s.fillna(0.0).cumsum()


def equity(net: pd.Series) -> pd.Series:
    return (1.0 + net.fillna(0.0)).cumprod()


def drawdown(net: pd.Series) -> pd.Series:
    curve = equity(net)
    return curve / curve.cummax() - 1.0


def rolling_sharpe(net: pd.Series, days: float) -> pd.Series:
    per_day = bars_per_day(net.index)
    window = max(2, int(round(days * per_day)))
    mean = net.rolling(window, min_periods=window // 2).mean()
    std = net.rolling(window, min_periods=window // 2).std()
    return mean / std.replace(0.0, np.nan) * np.sqrt(365.0 * per_day)


def max_drawdown(net: pd.Series) -> float:
    return float(drawdown(net).min()) if len(net) else float("nan")


def sharpe(net: pd.Series) -> float:
    net = net.dropna()
    if len(net) < 2 or net.std() == 0:
        return float("nan")
    return float(net.mean() / net.std() * np.sqrt(365.0 * bars_per_day(net.index)))


@dataclass(frozen=True)
class Options:
    """画图参数：组合、成本、各个滚动窗口（天）。"""

    combo: Combo = Combo()
    cost: str = "all_taker"
    ic_window_days: float = 20.0
    ic_long_window_days: float = 120.0
    sharpe_window_days: float = 90.0
    turnover_window_days: float = 20.0
    # RankIC 的持有期：None = 每个 run 用自己的主口径。多模型比较时由 `resolve_ic_horizon` 统一成大家都有的同一个口径
    ic_horizon: Optional[int] = None


# ---- 多模型比较的指标表：名字 -> (标题, 纵轴, 底层序列, 派生函数) ----

def _ic(run: RunSeries, opts: Options) -> Optional[pd.Series]:
    return run.ic(opts.ic_horizon)


def resolve_ic_horizon(runs: list[RunSeries], requested: Optional[int] = None) -> Optional[int]:
    """多个 run 的 RankIC 统一到同一个持有期：给了就用给的；没给时主口径都一样就用它，否则用大家都有的口径里最长的那个。

    1 根和 6 根的 RankIC 量级不同（持有越久，信号累积越多），不同口径放在一张图上比会误导，所以没有共同口径时报错。
    """
    with_ic = [run for run in runs if run.rank_ic is not None]
    if requested is not None or not with_ic:
        return requested
    mains = {run.ic_horizon for run in with_ic}
    if len(mains) == 1:
        return mains.pop()
    common = set.intersection(*(set(run.ic_by_horizon) for run in with_ic))
    if not common:
        detail = "、".join(f"{run.name}={sorted(run.ic_by_horizon) or '?'}" for run in with_ic)
        raise ValueError(f"这些 run 的 RankIC 没有共同的持有期（{detail}），用 --ic-horizon 指定一个大家都有的")
    return max(common)


def _net(run: RunSeries, opts: Options) -> Optional[pd.Series]:
    return None if run.gross is None else run.net_returns(opts.combo, opts.cost)


def _turnover(run: RunSeries, opts: Options) -> Optional[pd.Series]:
    return None if run.turnover is None else run.turnover[opts.combo.column(run.turnover.columns)]


@dataclass(frozen=True)
class Metric:
    title: str
    y_title: str
    source: Callable[[RunSeries, Options], Optional[pd.Series]]
    derive: Callable[[pd.Series, Options], pd.Series]
    percent: bool = False
    zero_line: bool = False


METRICS: dict[str, Metric] = {
    "rankic_rolling": Metric("滚动 RankIC（{ic_window_days:g} 天均值）", "RankIC", _ic,
                             lambda s, o: rolling_mean(s, o.ic_window_days), zero_line=True),
    "rankic_cum": Metric("累计 RankIC（斜率 = IC 水平，变平 = 衰减）", "累计 RankIC", _ic, lambda s, o: cumulative(s)),
    "rankic_diff_cum": Metric("相对基线的累计 RankIC 差（向上 = 比基线好）", "累计 RankIC 差", _ic, lambda s, o: cumulative(s),
                              zero_line=True),
    "equity": Metric("净值（{combo} · {cost}）", "净值", _net, lambda s, o: equity(s)),
    "drawdown": Metric("回撤（{combo} · {cost}）", "回撤", _net, lambda s, o: drawdown(s), percent=True),
    "sharpe_rolling": Metric("滚动净 Sharpe（{sharpe_window_days:g} 天，{combo} · {cost}）", "年化 Sharpe", _net,
                             lambda s, o: rolling_sharpe(s, o.sharpe_window_days), zero_line=True),
    "turnover": Metric("单边换手（{turnover_window_days:g} 天均值，{combo}）", "换手 / 根", _turnover,
                       lambda s, o: rolling_mean(s, o.turnover_window_days)),
}


def metric_title(name: str, opts: Options) -> str:
    title = METRICS[name].title.format(combo=opts.combo.label, cost=opts.cost, ic_window_days=opts.ic_window_days,
                                       sharpe_window_days=opts.sharpe_window_days,
                                       turnover_window_days=opts.turnover_window_days)
    if METRICS[name].source is _ic and opts.ic_horizon is not None:
        title += f" · 持有 {opts.ic_horizon} 根"
    return title


def compare_series(runs: list[RunSeries], name: str, opts: Options, baseline: Optional[RunSeries] = None) -> dict[str, pd.Series]:
    """多个 run 的同一个指标，先裁到共同区间再派生。`rankic_diff_cum` 要基线：每个模型的逐期 IC 减去基线同一期的 IC。"""
    metric = METRICS[name]
    raw = {run.name: metric.source(run, opts) for run in runs}
    raw = {k: v.dropna() for k, v in raw.items() if v is not None and v.notna().any()}
    if name == "rankic_diff_cum":
        base = None if baseline is None else baseline.ic(opts.ic_horizon)
        if base is None:
            raise ValueError("rankic_diff_cum 要指定有（这个持有期）RankIC 的基线（--baseline）")
        base = base.dropna()
        raw = {k: (v - base).dropna() for k, v in raw.items() if k != baseline.name}
    if not raw:
        return {}
    start = max(s.index[0] for s in raw.values())
    end = min(s.index[-1] for s in raw.values())
    return {k: metric.derive(v[(v.index >= start) & (v.index <= end)], opts) for k, v in raw.items()}


def segment_summary(run: RunSeries, opts: Options) -> pd.DataFrame:
    """每段一行：平均 RankIC、选定组合的净 Sharpe / 最大回撤 / 累计收益（图上的小结和命令行打印用）。"""
    bounds = sorted(run.segments.items(), key=lambda kv: kv[1])
    rows = []
    net = _net(run, opts)
    for i, (segment, start) in enumerate(bounds):
        end = bounds[i + 1][1] if i + 1 < len(bounds) else None
        def cut(s: pd.Series) -> pd.Series:
            return s[(s.index >= start) & ((s.index < end) if end is not None else True)]
        row = {"段": segment}
        ic = run.ic(opts.ic_horizon)
        if ic is not None:
            row["平均 RankIC"] = float(cut(ic).mean())
        if net is not None:
            n = cut(net)
            row.update({"净 Sharpe": sharpe(n), "最大回撤": max_drawdown(n), "累计收益": float(equity(n).iloc[-1] - 1.0)})
        rows.append(row)
    return pd.DataFrame(rows)
