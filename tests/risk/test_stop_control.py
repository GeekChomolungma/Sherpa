"""止损控制（`sherpa.risk.stop_control`）：黑盒"目标权重路径进、逐期持仓出"的几条约束，以及接进向量化回测后的口径。"""

import numpy as np
import pandas as pd
import pytest

from sherpa.backtest.cost_model import ZeroCostModel
from sherpa.backtest.score_backtest import target_path
from sherpa.backtest.vectorized import _drift, run_vectorized_backtest
from sherpa.risk.reentry import (AllOf, AnyOf, IcRecovered, MarketCalm, MarketTape, MaxFlat, ReentryContext, ShadowRebound,
                                 ShadowReboundScaled, ShadowRecovered, UnstoppedAboveMean)
from sherpa.risk.shadow_book import ShadowBook
from sherpa.risk.stop_control import BookStop, StopController, StopRules, SymbolStop, drawdown_limit

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
        seen.append((controller.equity, controller.unstopped_equity))
        held_prev, ret_prev = held, returns[i]
    equity = pd.Series([e for e, _ in seen], index=index)
    shadow = pd.Series([s for _, s in seen], index=index)
    expected = (1.0 + base.returns).cumprod().shift(shift).fillna(1.0)
    np.testing.assert_allclose(equity.to_numpy(), expected.to_numpy(), rtol=1e-10)
    np.testing.assert_allclose(shadow.to_numpy(), expected.to_numpy(), rtol=1e-10)


@pytest.mark.parametrize("rules", [
    StopRules(book=BookStop(max_drawdown=0.05, min_flat_bars=3, reentry=UnstoppedAboveMean(bars=12))),
    StopRules(symbol=SymbolStop(stop_loss=0.03)),
    StopRules(book=BookStop(max_drawdown=0.05, reentry=UnstoppedAboveMean(bars=12)), symbol=SymbolStop(stop_loss=0.03)),
    StopRules(book=BookStop(max_drawdown=0.05, min_flat_bars=2,
                            reentry=AllOf((ShadowRebound(0.03), MarketCalm(window=12, ratio=1.2))))),
    StopRules(book=BookStop(max_drawdown=0.05, min_flat_bars=2, reentry=ShadowRecovered(-0.02), shadow_follow_targets=False)),
    StopRules(book=BookStop(vol_mult=1.5, vol_bars=30)),
    StopRules(book=BookStop(vol_mult=1.0, vol_bars=30, reentry=AnyOf((AllOf((ShadowReboundScaled(0.5), MarketCalm(12))), MaxFlat(12))))),
])
def test_only_reduces_risk_and_is_point_in_time(rules):
    """每一期的实际持仓不超过不加止损时此刻会持有的仓位（调仓行 = 目标，非调仓行 = 漂移后的持仓；恢复那一根 = 最近一次
    目标按决策时刻已知的价格漂移到现在），同号且不放大；截掉后面的数据，前面的结果不变。"""
    close = _market(vol=0.05)
    rebalance, shift = 3, 2
    targets = _targets(close, rebalance)
    controller = StopController(rules, close.shape[1], shift=shift)
    prices, weights = close.to_numpy(), targets.to_numpy()
    returns = close.pct_change().shift(-shift).fillna(0.0).to_numpy()
    realized = close.pct_change().fillna(0.0).to_numpy()
    held_prev, ret_prev, reference = np.zeros(close.shape[1]), np.zeros(close.shape[1]), np.zeros(close.shape[1])
    for i in range(len(close) - shift):
        drifted = _drift(held_prev, ret_prev)
        trade = i % rebalance == 0
        reference = weights[i] if trade else _drift(reference, realized[i])
        allowed = [weights[i] if trade else drifted, reference]
        held = controller.step(close=prices[i], target=weights[i] if trade else None, holding=drifted)
        assert any(np.all(((held == 0) | (np.sign(held) == np.sign(b))) & (np.abs(held) <= np.abs(b) + 1e-12))
                   for b in allowed)
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
    rules = StopRules(book=BookStop(max_drawdown=0.10, min_flat_bars=3, reentry=UnstoppedAboveMean(bars=6)))
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


@pytest.mark.parametrize("shift", [1, 2])
@pytest.mark.parametrize("follow", [True, False])
def test_shadow_book_starts_from_the_snapshot_and_books_with_a_shift_lag(shift, follow):
    """影子组合：开端 = 熔断时的持仓快照，第 shift 步才记上它的第一根收益；之后跟随目标调仓（或冻结快照只漂移）。"""
    rng = np.random.default_rng(3)
    realized = rng.normal(0.0, 0.03, size=(12, 3))
    targets = [None, np.array([0.0, 0.5, -0.5]), None, None] * 3
    snapshot = np.array([0.5, -0.5, 0.0])
    shadow = ShadowBook(snapshot, shift=shift, follow_targets=follow)
    decisions = [snapshot] + [t if follow else None for t in targets]   # 第 k 步的决策（None = 不调仓）
    weights, ret_prev, equity = np.zeros(3), np.zeros(3), 1.0
    for i in range(len(targets)):
        shadow.settle(realized[i])
        k = i + 1 - shift   # 这一步记账的是第 k 步的决策
        if k >= 0:
            weights = decisions[k] if decisions[k] is not None else _drift(weights, ret_prev)
            equity *= 1.0 + weights @ realized[i]
            ret_prev = realized[i]
        assert shadow.equity == pytest.approx(equity, rel=1e-12)
        shadow.push(targets[i])
    assert shadow.bars == len(targets)
    assert shadow.trough == pytest.approx(min(shadow.path)) and shadow.peak == pytest.approx(max(shadow.path))


def _crash_and_rebound(n_down: int = 20, n_up: int = 30):
    n = 10 + n_down + n_up
    index = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC", name="start_time")
    bottom = 100.0 * 0.98 ** n_down
    path = np.concatenate([np.full(10, 100.0), 100.0 * 0.98 ** np.arange(1, n_down + 1), bottom * 1.02 ** np.arange(1, n_up + 1)])
    close = pd.DataFrame({"A": path, "B": np.full(n, 50.0)}, index=index)
    targets = pd.DataFrame({"A": 1.0, "B": 0.0}, index=index)
    return close, targets, index[10 + n_down - 1]


def test_shadow_rebound_resumes_right_after_the_bottom():
    """影子从熔断后的最低点反弹 5%（1.02³ ≈ 1.061）就恢复：比"全程净值站上 42 根均值"早得多，且事件里带影子读数。"""
    close, targets, bottom = _crash_and_rebound()
    fast = _run(close, targets, 1, 1, StopRules(book=BookStop(max_drawdown=0.10, min_flat_bars=3, reentry=ShadowRebound(0.05))))
    slow = _run(close, targets, 1, 1, StopRules(book=BookStop(max_drawdown=0.10, min_flat_bars=3, reentry=UnstoppedAboveMean(42))))
    events = fast.stop_events
    assert list(events["event"][:2]) == ["book_trip", "book_resume"]
    trip, resume = events.iloc[0], events.iloc[1]
    assert trip["shadow_equity"] == 1.0 and trip["flat_bars"] == 0
    assert resume["shadow_rebound"] >= 0.05 and resume["shadow_equity"] < 1.0   # 影子还没回到开端，但已从底部反弹
    bars_after_bottom = close.index.get_loc(resume["time"]) - close.index.get_loc(bottom)
    assert 3 <= bars_after_bottom <= 4
    slow_resume = slow.stop_events.query("event == 'book_resume'")["time"]
    assert slow_resume.empty or slow_resume.iloc[0] > resume["time"]
    assert fast.returns.sum() > slow.returns.sum()


def test_market_calm_compares_post_trip_vol_with_pre_trip_vol():
    tape = MarketTape()
    rng = np.random.default_rng(0)
    for scale in [0.05] * 20 + [0.01] * 20:   # 熔断时（第 20 根）大盘很乱，之后平静下来
        tape.append(rng.normal(0.0, scale, size=5), np.ones(5, dtype=bool))
    shadow = ShadowBook(np.zeros(5), shift=1)
    calm_now = ReentryContext(shadow=shadow, market=tape, market_at_trip=20, unstopped_path=[1.0])
    assert MarketCalm(window=10, ratio=0.5).ready(calm_now)
    assert not MarketCalm(window=10, ratio=0.5).ready(ReentryContext(shadow=shadow, market=tape, market_at_trip=30, unstopped_path=[1.0]))  # 熔断前后一样平静
    # 熔断后只用熔断后的数据：刚熔断、新数据不到 2 根时不恢复（不会拿熔断前的窗口凑数）
    assert not MarketCalm(window=10).ready(ReentryContext(shadow=shadow, market=tape, market_at_trip=39, unstopped_path=[1.0]))
    assert MarketCalm(window=10).ready(ReentryContext(shadow=shadow, market=tape, market_at_trip=38, unstopped_path=[1.0]))
    assert MarketCalm(window=10).ready(ReentryContext(shadow=shadow, market=tape, market_at_trip=5, unstopped_path=[1.0]))  # 熔断时数据不够：不拦


def test_ic_recovered_uses_only_post_trip_ic_against_the_pre_trip_level_and_the_floor():
    shadow = ShadowBook(np.zeros(5), shift=1)
    rule = IcRecovered(window=3, floor=0.03)

    def ctx(ic, at_trip):
        return ReentryContext(shadow=shadow, market=MarketTape(), market_at_trip=0, unstopped_path=[1.0], ic=ic, ic_at_trip=at_trip)

    assert not rule.ready(ctx([0.05, 0.03, 0.01, -0.02, -0.04, 0.01], 3))   # 熔断前均值 0.03，熔断后 -0.017
    assert rule.ready(ctx([0.05, 0.03, 0.01, 0.05, 0.08], 3))               # 熔断后才 2 根也能比：0.065 ≥ 0.03
    assert rule.ready(ctx([0.0, 0.0, 0.0, 0.05], 3))                        # 熔断后 1 根：0.05 ≥ max(0, 0.03)
    assert not rule.ready(ctx([-0.1, -0.1, -0.1, 0.02, 0.02], 3))           # 回到熔断前水平了，但没过硬门槛 0.03
    # 隔离：熔断前的高 IC 不能混进熔断后的均值（不隔离时 (0.2 + 0 + 0) / 3 = 0.067 就恢复了）
    assert not rule.ready(ctx([-0.3, 0.2, 0.2, 0.0, 0.0], 3))
    assert rule.ready(ctx([0.1, 0.04], 1))                                  # 熔断前不够一个窗口：只看 floor
    assert not rule.ready(ctx([0.1, 0.1, 0.1], 3))                          # 熔断后还没有新 IC
    assert not rule.ready(ctx([np.nan] * 6, 3))                             # 没传 IC：不恢复


@pytest.mark.parametrize("shift", [1, 2, 3])
def test_ic_reaches_the_controller_only_after_its_holding_period_is_realized(shift):
    """第 t 行的 IC 用到了第 t 行持有期的收益，要等第 t + shift 步才能看到：跟毛净值记账同一个延迟。"""
    close = _market(n_bars=30)
    controller = StopController(StopRules(book=BookStop(max_drawdown=0.999)), close.shape[1], shift=shift)
    ic = np.arange(len(close), dtype=float) / 100.0
    for i in range(len(close)):
        controller.step(close=close.iloc[i].to_numpy(), target=np.zeros(close.shape[1]), holding=np.zeros(close.shape[1]), ic=ic[i])
        assert controller.ic == list(ic[: max(i + 1 - shift, 0)])


def test_ic_rule_resumes_once_the_alpha_works_again():
    """熔断后 IC 一直为负就一直空仓；IC 转正、熔断后的均值过了硬门槛 0.03 才恢复。"""
    close, targets, bottom = _crash_and_rebound()
    ic = pd.Series(-0.05, index=close.index)
    turn = close.index.get_loc(bottom) + 10
    ic.iloc[turn:] = 0.04
    rules = StopRules(book=BookStop(max_drawdown=0.10, reentry=IcRecovered(window=3)))
    result = run_vectorized_backtest(targets, panel_from_close(close), lambda row: row, ZeroCostModel(),
                                     shift=1, rebalance_every=1, stop_rules=rules, ic=ic)
    events = result.stop_events
    assert list(events["event"][:2]) == ["book_trip", "book_resume"]
    resume_at = close.index.get_loc(events.iloc[1]["time"])
    # 第 turn 行的 IC 晚 1 步（shift）才知道；窗口 3：turn+1 步 (-0.05, -0.05, 0.04) 为负，turn+2 步 0.01 < 0.03，
    # turn+3 步 0.04 才过门槛
    assert resume_at == turn + 3


def test_stop_rules_round_trip_through_dict():
    rules = StopRules(book=BookStop(max_drawdown=0.12, min_flat_bars=2, shadow_follow_targets=False,
                                    reentry=AllOf((ShadowRebound(0.04), MarketCalm(window=30, ratio=0.8), IcRecovered(42, 0.01)))),
                      symbol=SymbolStop(0.05))
    assert StopRules.from_dict(rules.to_dict()) == rules
    assert StopRules.from_dict(StopRules(book=BookStop()).to_dict()).book == BookStop()


def test_drawdown_limit_scales_with_recent_volatility():
    rng = np.random.default_rng(0)
    returns = list(rng.normal(0.0, 0.01, size=200))
    assert np.isnan(drawdown_limit(returns[:179], vol_mult=1.5, vol_bars=180))
    expected = 1.5 * np.std(returns[-180:]) * np.sqrt(180)
    assert drawdown_limit(returns, vol_mult=1.5, vol_bars=180) == pytest.approx(expected)
    calm = returns[:20] + [r / 4 for r in returns[20:]]
    assert drawdown_limit(calm, vol_mult=1.5, vol_bars=180) == pytest.approx(expected / 4, rel=0.05)


def test_dynamic_threshold_trips_later_in_a_noisy_book():
    """同样跌 12%：波动小的组合（阈值低）熔断，波动大的组合（阈值高，1.5 × 30 天波动远超 12%）不熔断。"""
    def run(noise):
        n = 260
        index = pd.date_range("2026-01-01", periods=n, freq="4h", tz="UTC", name="start_time")
        wiggle = np.where(np.arange(n) % 2 == 0, 1 + noise, 1 / (1 + noise))
        drop = np.r_[np.ones(220), np.full(10, 0.987), np.ones(30)]
        close = pd.DataFrame({"A": 100.0 * np.cumprod(wiggle * drop), "B": np.full(n, 50.0)}, index=index)
        targets = pd.DataFrame({"A": 1.0, "B": 0.0}, index=index)
        return _run(close, targets, 1, 1, StopRules(book=BookStop(vol_mult=1.5, vol_bars=180, reentry=MaxFlat(1000))))
    quiet, noisy = run(0.002), run(0.03)
    assert (quiet.stop_events["event"] == "book_trip").sum() == 1
    assert quiet.stop_events["threshold"].iloc[0] < 0.12
    assert noisy.stop_events.empty


def test_resume_on_a_non_rebalance_row_goes_straight_back_to_full_position():
    """每 3 根调仓：熔断每根都判断（不在调仓行也当根清仓）；恢复那根不是调仓行也直接满仓，不等下一个调仓行。"""
    close, targets, _ = _crash_and_rebound()
    result = _run(close, targets, 3, 1, StopRules(book=BookStop(max_drawdown=0.10, reentry=ShadowRebound(0.05))))
    events = result.stop_events
    trip, resume = events["time"].iloc[0], events["time"].iloc[1]
    rows = {t: k for k, t in enumerate(result.returns.index)}
    assert rows[trip] % 3 != 0 or rows[resume] % 3 != 0  # 至少有一次落在非调仓行，检查才有意义
    assert result.turnover.loc[trip] == pytest.approx(1.0)     # 当根清仓
    assert result.turnover.loc[resume] == pytest.approx(1.0)   # 当根满仓
    assert result.returns.loc[resume] > 0


def test_high_water_is_recorded_but_never_reset():
    close, targets, _ = _crash_and_rebound()
    result = _run(close, targets, 1, 1, StopRules(book=BookStop(max_drawdown=0.10, reentry=ShadowRebound(0.05))))
    resume = result.stop_events.query("event == 'book_resume'").iloc[0]
    assert resume["drawdown"] == 0.0                    # 判断熔断用的峰值重置了
    assert resume["total_drawdown"] <= -0.10            # 相对历史最高点的总回撤还在
