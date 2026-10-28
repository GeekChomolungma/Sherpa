"""tradecraft 研究线的配置和通用的逐期 RankIC 时间线（research/alpha_research/_pipeline/run_ic_timeline.py）。"""

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

RESEARCH = Path(__file__).resolve().parents[2] / "research"
PIPELINE = RESEARCH / "alpha_research" / "_pipeline"
sys.path.insert(0, str(RESEARCH / "ml_training"))
sys.path.insert(0, str(RESEARCH / "_shared"))

import config as ml_config  # noqa: E402
from dataset import liquidity_from_tradable, plan_folds  # noqa: E402

from sherpa.alpha.custom.tradecraft import TRADECRAFT_LIQUIDITY  # noqa: E402
from sherpa.backtest.residual import ScorePreprocessor  # noqa: E402
from sherpa.metrics.factor import forward_returns, rank_ic  # noqa: E402


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _ic_timeline():
    # run_ic_timeline.py 按裸名 `from data import …` 取 _pipeline/data.py；ml_training/ 下也有一个 data.py，
    # 这里临时把 sys.modules["data"] 换成 _pipeline 那份，加载完再换回去
    saved = sys.modules.get("data")
    sys.modules["data"] = _load(PIPELINE / "data.py", "data")
    try:
        return _load(PIPELINE / "run_ic_timeline.py", "_tc_run_ic_timeline")
    finally:
        if saved is None:
            sys.modules.pop("data", None)
        else:
            sys.modules["data"] = saved


def test_track_mask_equals_the_tradecraft_liquidity_scope():
    """alpha 自己的流动性范围 = 研究线评估掩码：研究评估、回测、实盘看到的是同一批币。"""
    track = json.loads((RESEARCH / "alpha_research" / "tradecraft" / "track.json").read_text(encoding="utf-8"))
    assert liquidity_from_tradable(track["preprocess"]["tradable_mask"]) == TRADECRAFT_LIQUIDITY
    assert track["preprocess"]["neutralize"] is False
    assert track["stages"]["orthogonalization"]["mode"] == "passthrough"
    assert track["stages"]["synthesis"]["mode"] == "passthrough"


def test_timeline_blocks_line_up_with_the_ml_retraining_schedule():
    """时间线的 20 天时段跟 ML 的重训时点重合，`folds.csv` 能按 valid_from 逐段配对。"""
    timeline = _ic_timeline()
    assert timeline.BLOCK_BARS == ml_config.RETRAIN_EVERY_BARS
    assert timeline.ANCHOR_BARS == ml_config.MIN_TRAIN_BARS
    assert timeline.MIN_PERIOD_SYMBOLS == ml_config.MIN_PERIOD_ROWS
    start = pd.Timestamp("2023-01-01", tz="UTC")
    folds = plan_folds(research_start=start, last_bar=start + pd.Timedelta(days=500), interval="4h",
                       retrain_every_bars=ml_config.RETRAIN_EVERY_BARS, min_train_bars=ml_config.MIN_TRAIN_BARS, purge_bars=7)
    for fold in folds:
        inside = pd.DatetimeIndex([fold.valid_from, fold.valid_until - pd.Timedelta(hours=4)])
        assert (timeline.block_starts(inside, research_start=start, interval="4h") == fold.valid_from).all()
    first = timeline.block_starts(pd.DatetimeIndex([start]), research_start=start, interval="4h")[0]
    assert first == start  # 研究起点之后、第一个 ML 时段之前的数据也铺成整段


def _toy(n=400, n_symbols=30, seed=1):
    rng = np.random.default_rng(seed)
    index = pd.date_range("2023-01-01", periods=n, freq="4h", tz="UTC")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, n_symbols)), axis=0)), index=index,
                         columns=[f"S{i:02d}" for i in range(n_symbols)])
    score = -close.pct_change(1)  # 一个有点反转信号的打分
    score.iloc[:10] = np.nan  # 开头没有打分
    return close, score


def test_timeline_matches_rank_ic_and_its_summaries():
    timeline = _ic_timeline()
    close, score = _toy()
    preprocessor = ScorePreprocessor(mask=None, exposures=None)
    start = close.index[0]
    validation_start = close.index[250]
    by_bar = timeline.timeline(score, close, preprocessor, horizon=1, delay=1, research_start=start,
                               validation_start=validation_start, interval="4h")
    expected = rank_ic(score, forward_returns(close, horizon=1, delay=1))
    pd.testing.assert_series_equal(by_bar["rank_ic"], expected.loc[by_bar.index], check_names=False)
    pd.testing.assert_series_equal(by_bar["rank_ic"], by_bar["rank_ic_h1"], check_names=False)
    assert by_bar.index[0] == close.index[10]  # 从第一根有打分的 bar 开始
    assert ((by_bar["segment"] == "validation") == (by_bar.index >= validation_start)).all()

    folds, summary = timeline.summaries(by_bar, interval="4h")
    per_block = by_bar.groupby("fold_valid_from")["rank_ic"].mean()
    np.testing.assert_allclose(folds.set_index("valid_from").loc[per_block.index, "rank_ic_mean"], per_block)
    overall = summary.set_index("segment").loc["all"]
    assert overall["periods"] == by_bar["rank_ic"].notna().sum()
    assert np.isclose(overall["rank_ic_mean"], by_bar["rank_ic"].mean())


def test_timeline_uses_the_alpha_horizon_for_the_main_column():
    timeline = _ic_timeline()
    close, score = _toy()
    by_bar = timeline.timeline(score, close, ScorePreprocessor(), horizon=3, delay=1, research_start=close.index[0],
                               validation_start=close.index[250], interval="4h")
    expected = rank_ic(score, forward_returns(close, horizon=3, delay=1))
    pd.testing.assert_series_equal(by_bar["rank_ic"], expected.loc[by_bar.index], check_names=False)
    assert {"rank_ic_h1", "rank_ic_h6"} <= set(by_bar.columns)
    assert not np.allclose(by_bar["rank_ic"].fillna(0), by_bar["rank_ic_h1"].fillna(0))
