import numpy as np
import pandas as pd

from sherpa.alpha.base import Alpha
from sherpa.alpha.engine import AlphaEngine
from sherpa.backtest.screening import screen_alphas
from sherpa.data.schema import BarPanel


def _synthetic_panel(n_periods=40, n_symbols=12, seed=0):
    # forward_returns 直接由 base 构造（加一点小噪声），不经过"对 close 做 pct_change"
    # 这一步——base 本身在时间轴上是常量（tile 出来的，只在 symbol 轴上变化），如果先叠成
    # close 再差分，base 的信号会在差分时被消掉，只剩下噪声，导致这个本该是"强信号"的因子
    # 反而测不出预测力。直接构造 forward_returns 才是这里真正要测的东西：
    # "alpha_history 和 forward_returns 排序一致时，alpha_check 应该判通过"。
    rng = np.random.default_rng(seed)
    index = pd.date_range("2026-01-01", periods=n_periods, freq="1min", tz="UTC")
    columns = [f"SYM{i}" for i in range(n_symbols)]
    base = np.tile(np.arange(n_symbols, dtype=float), (n_periods, 1))
    forward_returns = pd.DataFrame(base * 0.01 + rng.normal(0, 0.001, size=base.shape), index=index, columns=columns)
    return index, columns, base, forward_returns


class _StrongAlpha(Alpha):
    """跟未来收益完全同向排序的因子——预期 alpha_check 会通过。"""

    name = "strong"
    family = "custom"

    def __init__(self, base: pd.DataFrame, index, columns):
        super().__init__()
        self._history = pd.DataFrame(base, index=index, columns=columns)

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return self._history


class _NoiseAlpha(Alpha):
    """跟未来收益无关的纯噪声——预期 alpha_check 不通过。"""

    name = "noise"
    family = "custom"

    def __init__(self, index, columns, seed=99):
        super().__init__()
        rng = np.random.default_rng(seed)
        self._history = pd.DataFrame(rng.normal(size=(len(index), len(columns))), index=index, columns=columns)

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        return self._history


class _BlockedAlpha(Alpha):
    """模拟世坤101里因缺字段占位不实现的因子。"""

    name = "blocked"
    family = "custom"

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        raise NotImplementedError("blocked 依赖 BarPanel 不支持的字段")


def _make_panel_for_engine(index, columns):
    """screen_alphas 只用 panel 传给 alpha.compute()，这里的 alpha 都不读 panel 内容，
    随便给一个结构合法的空壳即可（复用 tests/alpha/fixtures 的合成面板更省事）。"""
    from tests.alpha.fixtures import make_panel

    return make_panel(n=len(index), symbols=tuple(columns))


def test_screen_alphas_ranks_by_ic_ir_and_marks_pass_fail():
    index, columns, base, forward_returns = _synthetic_panel()
    panel = _make_panel_for_engine(index, columns)

    engine = AlphaEngine([_StrongAlpha(base, index, columns), _NoiseAlpha(index, columns)])
    report = screen_alphas(engine, panel, forward_returns, ic_ir_threshold=0.5)

    assert list(report.table.index) == ["custom.strong", "custom.noise"]
    assert bool(report.table.loc["custom.strong", "passed"]) is True
    assert report.errors == {}


def test_screen_alphas_isolates_not_implemented_alphas_into_errors():
    index, columns, base, forward_returns = _synthetic_panel()
    panel = _make_panel_for_engine(index, columns)

    engine = AlphaEngine([_StrongAlpha(base, index, columns), _BlockedAlpha()])
    report = screen_alphas(engine, panel, forward_returns)

    assert list(report.table.index) == ["custom.strong"]
    assert "custom.blocked" in report.errors
    assert "不支持" in report.errors["custom.blocked"]


def test_screen_alphas_empty_engine_gives_empty_report():
    index, columns, _base, forward_returns = _synthetic_panel()
    panel = _make_panel_for_engine(index, columns)

    report = screen_alphas(AlphaEngine([]), panel, forward_returns)

    assert report.table.empty
    assert report.errors == {}


def test_screen_alphas_table_has_expected_columns():
    index, columns, base, forward_returns = _synthetic_panel()
    panel = _make_panel_for_engine(index, columns)

    engine = AlphaEngine([_StrongAlpha(base, index, columns)])
    report = screen_alphas(engine, panel, forward_returns)

    assert list(report.table.columns) == ["ic_mean", "ic_std", "ic_ir", "passed"]
