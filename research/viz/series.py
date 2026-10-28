"""可视化的数据层：一个 run 的时间序列装进统一的 `RunSeries`，画图只认它，不关心数据是哪个阶段产出的。

现在只有研究线的加载器（`load_research_run`，读 `runs/<run_id>/results_*/` 下的逐期文件）。以后阶段二回测要接进来，
只需再写一个加载器把回测结果填进同一个 `RunSeries`（回测的 `BacktestResult` 本来就有逐 bar 收益和换手），画图部分不用动。

`RunSeries` 里放的都是**最底层的逐期序列**（RankIC、毛收益、换手），净收益、净值、回撤、滚动 Sharpe 都是画图时按选定的
组合和成本现算的（`metrics.py`）：成本是换手的线性函数，净收益 = 毛收益 − 换手 × 成本 bps / 10000。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pandas as pd

# 默认组合：多模型比较 PnL 时所有模型都用这同一个组合（不能各挑各的最好那格，那等于在验证段上挑过一遍）
DEFAULT_WEIGHTING = "top10_exit20"
DEFAULT_REBALANCE_EVERY = 6
DEFAULT_COST = "all_taker"

RESULTS_DIR = "results_without_neutralization"


@dataclass(frozen=True)
class Combo:
    """组合构建方式：权重映射 + 调仓间隔（根 bar）。一个 run 里有多个 case（多个模型一起评估）时用 `case` 指定是哪个。"""

    weighting: str = DEFAULT_WEIGHTING
    rebalance_every: int = DEFAULT_REBALANCE_EVERY
    case: Optional[str] = None

    @property
    def label(self) -> str:
        return f"{self.weighting} / 每 {self.rebalance_every} 根"

    def column(self, columns: pd.Index) -> str:
        """在 `07` / `08` 的列（`<case> | <weighting> | every<N>`）里找到这个组合。"""
        suffix = f" | {self.weighting} | every{self.rebalance_every}"
        hits = [c for c in columns if c.endswith(suffix) and (self.case is None or c.split(" | ")[0] == self.case)]
        if not hits:
            raise KeyError(f"没有组合 {self.weighting} / every{self.rebalance_every}"
                           + (f"（case {self.case}）" if self.case else "") + f"；可选的有 {available_combos(columns)}")
        if len(hits) > 1:
            raise KeyError(f"组合 {self.label} 在多个 case 里都有：{[h.split(' | ')[0] for h in hits]}，用 case 指定一个")
        return hits[0]


def available_combos(columns: pd.Index) -> list[str]:
    return sorted({" | ".join(c.split(" | ")[1:]) for c in columns})


@dataclass(frozen=True)
class RunSeries:
    """一个 run 的逐期时间序列（阶段无关）。没有的部分留 None，画图时对应的子图会写"无数据"。

    - `rank_ic`：逐期样本外 RankIC（index = 时间）；
    - `gross` / `turnover`：逐 bar 毛收益 / 单边换手，宽表（列 = 组合）；
    - `cost_bps`：{成本假设名: 单边成本 bps}；
    - `segments`：{段名: 起点}，按起点排好序（研究线是 选择段 / 验证段），画背景色用；
    - `events`：值得在图上标竖线的时点（研究线 = ML 模型的重训时点）。
    """

    name: str
    stage: str
    source: Path
    rank_ic: Optional[pd.Series] = None
    gross: Optional[pd.DataFrame] = None
    turnover: Optional[pd.DataFrame] = None
    cost_bps: dict[str, float] = field(default_factory=dict)
    segments: dict[str, pd.Timestamp] = field(default_factory=dict)
    events: pd.DatetimeIndex = field(default_factory=lambda: pd.DatetimeIndex([], tz="UTC"))
    notes: dict[str, str] = field(default_factory=dict)

    def net_returns(self, combo: Combo, cost: str) -> pd.Series:
        """选定组合在选定成本假设下的逐 bar 净收益。"""
        if self.gross is None or self.turnover is None:
            raise ValueError(f"{self.name} 没有逐 bar 收益数据")
        if cost not in self.cost_bps:
            raise KeyError(f"没有成本假设 {cost!r}；可选的有 {list(self.cost_bps)}")
        column = combo.column(self.gross.columns)
        return self.gross[column] - self.turnover[column] * self.cost_bps[cost] / 10_000.0

    def all_net_returns(self, cost: str, case: Optional[str] = None) -> pd.DataFrame:
        """同一个 case 的全部组合在选定成本下的逐 bar 净收益（画"组合分布带"用）。"""
        if self.gross is None or self.turnover is None:
            raise ValueError(f"{self.name} 没有逐 bar 收益数据")
        columns = [c for c in self.gross.columns if case is None or c.split(" | ")[0] == case]
        return self.gross[columns] - self.turnover[columns] * self.cost_bps[cost] / 10_000.0


def _read_time_csv(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, index_col=0)
    frame.index = pd.to_datetime(frame.index, utc=True)
    return frame


def _results_dir(run_dir: Path, results: str) -> Path:
    candidates = [run_dir / results, run_dir]
    for path in candidates:
        if (path / "friction").is_dir() or (path / "ml_training").is_dir():
            return path
    raise FileNotFoundError(f"{run_dir} 下找不到研究线结果目录（{results}/friction 或 {results}/ml_training）")


def load_research_run(run_dir: str | Path, *, results: str = RESULTS_DIR) -> RunSeries:
    """读一个研究线 run（`<研究线>/runs/<run_id>/`）的逐期文件：

    - `ml_training/<model>_ic_by_bar.csv`：逐期样本外 RankIC（只有 ML 模型有）；`<model>_folds.csv` 的重训时点做竖线；
    - `friction/07_bar_gross_returns.csv`、`08_bar_turnover.csv`、`bar_series.json`：全部组合的逐 bar 毛收益、换手、成本口径。

    这些文件是 2026-10-27 起训练步骤 / 关卡3 才落盘的；旧 run 没有的话按提示重跑研究线（模型已训练好时步骤 0 只评估、不重训）。
    """
    run_dir = Path(run_dir).resolve()
    base = _results_dir(run_dir, results)
    rank_ic = None
    events = pd.DatetimeIndex([], tz="UTC")
    notes: dict[str, str] = {}

    ic_files = sorted((base / "ml_training").glob("*_ic_by_bar.csv"))
    if len(ic_files) > 1:
        raise ValueError(f"{base / 'ml_training'} 里有多个模型的逐期 RankIC：{[p.name for p in ic_files]}，可视化一次只看一个模型")
    ic_frame = None
    if ic_files:
        ic_frame = _read_time_csv(ic_files[0])
        rank_ic = ic_frame["rank_ic"]
        folds = sorted((base / "ml_training").glob("*_folds.csv"))
        if folds:
            events = pd.DatetimeIndex(pd.to_datetime(pd.read_csv(folds[0])["valid_from"], utc=True))
        config = sorted((base / "ml_training").glob("*_train_config.json"))
        if config:
            notes["训练窗口"] = json.loads(config[0].read_text(encoding="utf-8")).get("train_window", "")
    elif (base / "ml_training").is_dir():
        notes["缺数据"] = "没有 ml_training/*_ic_by_bar.csv：重跑一次研究线（模型已训练好时只评估、不重训）"

    gross = turnover = None
    cost_bps: dict[str, float] = {}
    segments: dict[str, pd.Timestamp] = {}
    friction = base / "friction"
    if (friction / "07_bar_gross_returns.csv").exists():
        gross = _read_time_csv(friction / "07_bar_gross_returns.csv")
        turnover = _read_time_csv(friction / "08_bar_turnover.csv").reindex_like(gross)
        meta = json.loads((friction / "bar_series.json").read_text(encoding="utf-8"))
        cost_bps = {name: float(bps) for name, bps in meta["cost_bps"].items()}
        start = min(s.index[0] for s in (gross, rank_ic) if s is not None)
        segments = {"选择段": start, "验证段": pd.Timestamp(meta["validation_start"])}
    elif friction.is_dir():
        notes["缺数据"] = "没有 friction/07_bar_gross_returns.csv：重跑关卡3（run_track.sh --from-step 5）"
    if not segments and ic_frame is not None:  # 没有关卡3 的文件时，分段取 ic_by_bar.csv 的 segment 列
        names = {"selection": "选择段", "validation": "验证段"}
        firsts = ic_frame.reset_index().groupby("segment")["time"].min()
        segments = {names.get(k, k): v for k, v in firsts.sort_values().items()}

    return RunSeries(name=run_dir.name, stage="research", source=run_dir, rank_ic=rank_ic, gross=gross, turnover=turnover,
                     cost_bps=cost_bps, segments=segments, events=events, notes=notes)


MARKET_DIR = Path(__file__).resolve().parent / "market"
DEFAULT_MARKET = "BTCUSDT"


def load_market(symbol: str = DEFAULT_MARKET, interval: str = "4h") -> Optional[pd.Series]:
    """画图用的市场背景（收盘价，`fetch_market.py` 从 ClickHouse 取的）。跟 run 无关，所以不在 `RunSeries` 里；没取过就返回 None。"""
    path = MARKET_DIR / f"{symbol}_{interval}.csv"
    if not path.exists():
        return None
    close = _read_time_csv(path)["close"]
    close.name = symbol
    return close


def load_run(path: str | Path) -> RunSeries:
    """按目录内容挑加载器。现在只有研究线；以后加阶段二回测时在这里按目录结构分派。"""
    return load_research_run(path)
