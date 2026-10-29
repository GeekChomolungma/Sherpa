"""止损控制（`sherpa.risk.stop_control`）：黑盒"目标权重路径进、逐期持仓出"的几条约束，以及接进向量化回测后的口径。"""

import numpy as np
import pandas as pd
import pytest

from sherpa.backtest.cost_model import ZeroCostModel
from sherpa.backtest.score_backtest import target_path
from sherpa.backtest.vectorized import _drift, run_vectorized_backtest
from sherpa.risk.stop_control import BookStop, StopController, StopRules, SymbolStop

from ..backtest.fixtures import panel_from_close

SPEC = {"method": "top_k", "k": 2, "exit_k": 3}


def _market(n_bars: int = 400, n_symbols: int = 8, seed: int = 0, vol: float = 0.03) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n_bars, freq="4h", tz="UTC", name="start_time")
    steps = rng.normal(0.0, vol, size=(n_bars, n_symbols))
    return pd.DataFrame(100.0 * np.exp(np.cumsum(steps, axis=0)), index=index, columns=[f"S{j}" for j in range(n_symbols)])


def _targets(close: pd.DataFrame, rebalance_every: int, seed: int = 1) -> pd.DataFrame:
    scores = pd.DataFrame(np.random.default_rng(seed).normal(size=close.shape), index=close.index, columns=close.columns)
    return target_path(scores, SPEC, rebalance_every)


def _run(close, targets, rebalance_every, shift, rules):
    return run_vectorized_backtest(targets, panel_from_close(close), lambda row: row, ZeroCostModel(),
                                   shift=shift, rebalance_every=rebalance_every, stop_rules=rules)


@pytest.mark.parametrize("rules", [None, StopRules()])
def test_no_rules_leaves_the_backtest_untouched(rules):
    close = _market()
    targets = _targets(close, 3)
    base = _run(close, targets, 3, 2, None)
    result = _run(close, targets, 3, 2, rules)
    pd.testing.assert_series_equal(result.returns, base.returns)
    pd.testing.assert_series_equal(result.turnover, base.turnover)
    assert result.stop_events is None


@pytest.mark.parametrize("shift", [1, 2, 3])
def test_book_equity_matches_the_backtest_gross_returns_lagged_by_shift(shift):
    """控制器自己用决策时刻的收盘价递推的毛净值 = 回测引擎的逐 bar 毛收益，晚 shift 步看到（不偷看未来）；
    影子净值 = 不加止损的同一条目标路径。规则设成永远不触发，逐步核对。"""
    close = _market()
    rebalance = 3
    targets = _targets(close, rebalance)
    base = _run(close, targets, rebalance, shift, None)
    controller = StopController(StopRules(book=BookStop(max_drawdown=0.999)), close.shape[1], shift=shift)
    index = base.returns.index
    weights, prices = targets.loc[index].to_numpy(), close.loc[index].to_numpy()
    returns = close.pct_change().shift(-shift).loc[index].fillna(0.0).to_numpy()
    held_prev, ret_prev, seen = np.zeros(close.shape[1]), np.zeros(close.shape[1]), []
    for i in range(len(index)):
        drifted = _drift(held_prev, ret_prev)
        trade = i % rebalance == 0
        held = controller.step(close=prices[i], target=weights[i] if trade else None, holding=drifted)
        seen.append((controller.equity, controller.shadow_equity))
        held_prev, ret_prev = held, returns[i]
    equity = pd.Series([e for e, _ in seen], index=index)
    shadow = pd.Series([s for _, s in seen], index=index)
    expected = (1.0 + base.returns).cumprod().shift(shift).fillna(1.0)
    np.testing.assert_allclose(equity.to_numpy(), expected.to_numpy(), rtol=1e-10)
    np.testing.assert_allclose(shadow.to_numpy(), expected.to_numpy(), rtol=1e-10)


@pytest.mark.parametrize("rules", [
    StopRules(book=BookStop(max_drawdown=0.05, resume_bars=12, min_flat_bars=3)),
    StopRules(symbol=SymbolStop(stop_loss=0.03)),
    StopRules(book=BookStop(max_drawdown=0.05, resume_bars=12), symbol=SymbolStop(stop_loss=0.03)),
])
def test_only_reduces_risk_and_is_point_in_time(rules):
    """每一期的实际持仓相对基础仓位（调仓行 = 目标，非调仓行 = 漂移后的持仓）同号且不放大；截掉后面的数据，前面的结果不变。"""
    close = _market(vol=0.05)
    rebalance, shift = 3, 2
    targets = _targets(close, rebalance)
    controller = StopController(rules, close.shape[1], shift=shift)
    prices, weights = close.to_numpy(), targets.to_numpy()
    returns = close.pct_change().shift(-shift).fillna(0.0).to_numpy()
    held_prev, ret_prev = np.zeros(close.shape[1]), np.zeros(close.shape[1])
    for i in range(len(close) - shift):
        drifted = _drift(held_prev, ret_prev)
        base = weights[i] if i % rebalance == 0 else drifted
        held = controller.step(close=prices[i], target=weights[i] if i % rebalance == 0 else None, holding=drifted)
        assert np.all((held == 0) | (np.sign(held) == np.sign(base)))
        assert np.all(np.abs(held) <= np.abs(base) + 1e-12)
        held_prev, ret_prev = held, returns[i]
    assert controller.events  # 这组参数在这份数据上真的触发过，上面的检查才有意义

    full = _run(close, targets, rebalance, shift, rules)
    cut = 300
    part = _run(close.iloc[:cut], targets.iloc[:cut], rebalance, shift, rules)
    pd.testing.assert_series_equal(full.returns.loc[part.returns.index], part.returns)


def test_book_trip_flattens_everything_and_resumes_after_shadow_recovers():
    """一个币持续下跌：回撤到阈值当根全部平掉（之后一直空仓），跌完反弹、影子净值站回均线后在调仓行重新建仓。"""
    n = 80
    index = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC", name="start_time")
    path = np.concatenate([np.full(10, 100.0), 100.0 * 0.98 ** np.arange(1, 21), 66.8 * 1.02 ** np.arange(1, 51)])
    close = pd.DataFrame({"A": path, "B": np.full(n, 50.0)}, index=index)
    targets = pd.DataFrame({"A": 1.0, "B": 0.0}, index=index)
    rules = StopRules(book=BookStop(max_drawdown=0.10, resume_bars=6, min_flat_bars=3))
    result = _run(close, targets, 1, 1, rules)
    events = result.stop_events
    assert list(events["event"][:2]) == ["book_trip", "book_resume"]
    trip, resume = events["time"].iloc[0], events["time"].iloc[1]
    assert events["drawdown"].iloc[0] <= -0.10
    flat = result.returns[(result.returns.index >= trip) & (result.returns.index < resume)]
    assert (flat == 0).all() and len(flat) >= 3
    assert result.returns[result.returns.index >= resume].gt(0).all()  # 恢复后跟上反弹


def test_symbol_stop_locks_until_the_signal_resets():
    """单币止损：浮亏到阈值平掉；目标里还要它（同一个信号的延续）不买回；目标里没了再回来才算新的进场。"""
    index = pd.date_range("2026-01-01", periods=8, freq="4h", tz="UTC", name="start_time")
    close = pd.DataFrame({"A": [100, 96, 91, 90, 92, 93, 95, 97.0]}, index=index)
    target = np.array([[1.0], [1.0], [1.0], [1.0], [0.0], [1.0], [1.0], [1.0]])
    controller = StopController(StopRules(symbol=SymbolStop(stop_loss=0.08)), 1, shift=1)
    held = [controller.step(close=close["A"].to_numpy()[i:i + 1], target=target[i], holding=target[i], label=index[i])[0]
            for i in range(len(index))]
    assert held == [1.0, 1.0, 0.0, 0.0, 0.0, 1.0, 1.0, 1.0]
    events = controller.events_frame()
    assert list(events["event"]) == ["symbol_stop"] and events["time"].iloc[0] == index[2]
    assert events["pnl"].iloc[0] == pytest.approx(-0.09)
