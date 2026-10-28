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
# 收益从哪个"账本"读：friction = 关卡3（多空对称的 39 个组合，所有研究线都有）；long_only = tradecraft 研究线的只做多回测
# （`research/alpha_research/tradecraft/run_long_only.py`，含等权基准）。两者文件格式相同
BOOKS = ("friction", "long_only")


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

    - `rank_ic`：逐期样本外 RankIC（index = 时间），持有期 = `ic_horizon` 根；
    - `ic_by_horizon`：{持有期: 逐期 RankIC}，含 `rank_ic` 本身和其它口径（不训练的研究线另有 1 根 / 6 根两列）。
      不同 run 的 RankIC 要按**同一个持有期**比（ML 主指标是 6 根，tradecraft 默认 1 根）；
    - `gross` / `turnover`：逐 bar 毛收益 / 单边换手，宽表（列 = 组合）；
    - `cost_bps`：{成本假设名: 单边成本 bps}；
    - `segments`：{段名: 起点}，按起点排好序（研究线是 选择段 / 验证段），画背景色用；
    - `events`：值得在图上标竖线的时点（研究线 = ML 模型的重训时点）。
    """

    name: str
    stage: str
    source: Path
    rank_ic: Optional[pd.Series] = None
    ic_horizon: Optional[int] = None
    ic_by_horizon: dict[int, pd.Series] = field(default_factory=dict)
    gross: Optional[pd.DataFrame] = None
    turnover: Optional[pd.DataFrame] = None
    cost_bps: dict[str, float] = field(default_factory=dict)
    segments: dict[str, pd.Timestamp] = field(default_factory=dict)
    events: pd.DatetimeIndex = field(default_factory=lambda: pd.DatetimeIndex([], tz="UTC"))
    notes: dict[str, str] = field(default_factory=dict)
    book: str = "friction"
    default_combo: Optional[Combo] = None  # 账本自己声明的默认组合（只做多账本没有关卡3 的 top10_exit20 / 每 6 根）

    def ic(self, horizon: Optional[int] = None) -> Optional[pd.Series]:
        """指定持有期的逐期 RankIC；`None` = 这个 run 的主口径。没有这个口径就返回 None。"""
        return self.rank_ic if horizon is None else self.ic_by_horizon.get(horizon)

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
        if any((path / stage).is_dir() for stage in ("friction", "ml_training", "ic_timeline", "long_only")):
            return path
    raise FileNotFoundError(f"{run_dir} 下找不到研究线结果目录（{results}/friction 或 {results}/ml_training）")


def load_research_run(run_dir: str | Path, *, results: str = RESULTS_DIR, book: str = "friction") -> RunSeries:
    """读一个研究线 run（`<研究线>/runs/<run_id>/`）的逐期文件：

    - 逐期 RankIC：ML 研究线在 `ml_training/<model>_ic_by_bar.csv`（训练步骤产出，持有期 = 训练标签，`<model>_folds.csv`
      的重训时点做竖线）；不训练的研究线（tradecraft 等）在 `ic_timeline/<name>_ic_by_bar.csv`（步骤 0 产出，主列 = alpha
      自己的持有期，另有 `rank_ic_h1` / `rank_ic_h6` 两列）；
    - `friction/07_bar_gross_returns.csv`、`08_bar_turnover.csv`、`bar_series.json`：全部组合的逐 bar 毛收益、换手、成本口径。

    这些文件是 2026-10-27 起训练步骤 / 关卡3 才落盘的；旧 run 没有的话按提示重跑研究线（模型已训练好时步骤 0 只评估、不重训）。
    """
    run_dir = Path(run_dir).resolve()
    base = _results_dir(run_dir, results)
    rank_ic = None
    ic_horizon = None
    ic_by_horizon: dict[int, pd.Series] = {}
    events = pd.DatetimeIndex([], tz="UTC")
    notes: dict[str, str] = {}

    ic_files = sorted((base / "ml_training").glob("*_ic_by_bar.csv")) + sorted((base / "ic_timeline").glob("*_ic_by_bar.csv"))
    if len(ic_files) > 1:
        raise ValueError(f"{base} 里有多个逐期 RankIC 文件：{[p.name for p in ic_files]}，可视化一次只看一个 alpha")
    ic_frame = None
    if ic_files:
        ic_frame = _read_time_csv(ic_files[0])
        rank_ic = ic_frame["rank_ic"]
        prefix = ic_files[0].name.removesuffix("_ic_by_bar.csv")
        if ic_files[0].parent.name == "ml_training":
            folds = ic_files[0].parent / f"{prefix}_folds.csv"
            if folds.exists():
                events = pd.DatetimeIndex(pd.to_datetime(pd.read_csv(folds)["valid_from"], utc=True))
            config = ic_files[0].parent / f"{prefix}_train_config.json"
            if config.exists():
                payload = json.loads(config.read_text(encoding="utf-8"))
                notes["训练窗口"] = payload.get("train_window", "")
                ic_horizon = payload.get("config", {}).get("label_horizon_bars")
        else:
            meta = ic_files[0].parent / f"{prefix}_ic_timeline.json"
            if meta.exists():
                ic_horizon = json.loads(meta.read_text(encoding="utf-8")).get("horizon_bars")
            for column in ic_frame.columns:
                if column.startswith("rank_ic_h"):
                    ic_by_horizon[int(column.removeprefix("rank_ic_h"))] = ic_frame[column]
        if ic_horizon is not None:
            ic_horizon = int(ic_horizon)
            ic_by_horizon[ic_horizon] = rank_ic
            others = [str(h) for h in sorted(ic_by_horizon) if h != ic_horizon]
            notes["RankIC 口径"] = f"持有 {ic_horizon} 根" + (f"（另有 {'、'.join(others)} 根）" if others else "")
    elif (base / "ml_training").is_dir():
        notes["缺数据"] = "没有 ml_training/*_ic_by_bar.csv：重跑一次研究线（模型已训练好时只评估、不重训）"
    elif (base / "friction").is_dir():
        notes["缺数据"] = "没有逐期 RankIC（ml_training/ 或 ic_timeline/ 下的 *_ic_by_bar.csv）"

    if book not in BOOKS:
        raise ValueError(f"book 只能是 {BOOKS}，收到 {book!r}")
    gross = turnover = None
    default_combo = None
    cost_bps: dict[str, float] = {}
    segments: dict[str, pd.Timestamp] = {}
    pnl_dir = base / book
    if (pnl_dir / "07_bar_gross_returns.csv").exists():
        gross = _read_time_csv(pnl_dir / "07_bar_gross_returns.csv")
        turnover = _read_time_csv(pnl_dir / "08_bar_turnover.csv").reindex_like(gross)
        meta = json.loads((pnl_dir / "bar_series.json").read_text(encoding="utf-8"))
        cost_bps = {name: float(bps) for name, bps in meta["cost_bps"].items()}
        start = min(s.index[0] for s in (gross, rank_ic) if s is not None)
        segments = {"选择段": start, "验证段": pd.Timestamp(meta["validation_start"])}
        if "default_weighting" in meta:
            default_combo = Combo(meta["default_weighting"], int(meta["default_rebalance_every"]))
        if book != "friction":
            notes["账本"] = f"{book}（{meta.get('description', '')}）"
    elif book != "friction":
        notes["缺数据"] = f"没有 {book}/07_bar_gross_returns.csv（只有 tradecraft 研究线的步骤 6 会产出）"
    elif pnl_dir.is_dir():
        notes["缺数据"] = "没有 friction/07_bar_gross_returns.csv：重跑关卡3（run_track.sh --from-step 5）"
    if not segments and ic_frame is not None:  # 没有关卡3 的文件时，分段取 ic_by_bar.csv 的 segment 列
        names = {"selection": "选择段", "validation": "验证段"}
        firsts = ic_frame.reset_index().groupby("segment")["time"].min()
        segments = {names.get(k, k): v for k, v in firsts.sort_values().items()}

    return RunSeries(name=run_dir.name, stage="research", source=run_dir, rank_ic=rank_ic, ic_horizon=ic_horizon,
                     ic_by_horizon=ic_by_horizon, gross=gross, turnover=turnover,
                     cost_bps=cost_bps, segments=segments, events=events, notes=notes, book=book, default_combo=default_combo)


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


def load_run(path: str | Path, book: str = "friction") -> RunSeries:
    """按目录内容挑加载器。现在只有研究线；以后加阶段二回测时在这里按目录结构分派。"""
    return load_research_run(path, book=book)
