import pandas as pd
import pytest

from sherpa.alpha.base import (
    Alpha,
    AlphaRegistry,
    CustomAlpha,
    TradingViewIndicator,
    WorldQuantAlpha,
    custom_alpha,
    register_alpha,
)
from sherpa.data.schema import empty_panel

from .fixtures import make_panel


class _Echo(Alpha):
    """测试用最小 Alpha：直接回传 close。"""

    def compute(self, panel):
        return panel.close


def test_base_compute_not_implemented():
    class _Bare(Alpha):
        pass

    with pytest.raises(NotImplementedError):
        _Bare().compute(make_panel(n=5))


def test_default_name_derives_from_class_name():
    a = _Echo()
    assert a.name == "_Echo"
    assert a.family == "custom"
    assert a.qualified_name == "custom._Echo"


def test_explicit_name_is_kept():
    class _Named(Alpha):
        name = "my_name"

        def compute(self, panel):
            return panel.close

    assert _Named().name == "my_name"


def test_latest_returns_last_row():
    panel = make_panel(n=5)
    a = _Echo()
    latest = a.latest(panel)
    pd.testing.assert_series_equal(latest, panel.close.iloc[-1], check_names=False)


def test_latest_on_empty_panel_returns_nan_series_indexed_by_symbols():
    panel = empty_panel("1m", ["BTCUSDT", "ETHUSDT"])
    a = _Echo()
    latest = a.latest(panel)
    assert list(latest.index) == list(panel.symbols)
    assert latest.isna().all()


def test_family_base_classes_set_family():
    assert WorldQuantAlpha.family == "worldquant"
    assert TradingViewIndicator.family == "tradingview"
    assert CustomAlpha.family == "custom"


def test_registry_register_and_get():
    registry = AlphaRegistry()

    class Foo(Alpha):
        name = "foo"
        family = "custom"

        def compute(self, panel):
            return panel.close

    registry.register(Foo)
    assert registry.get("custom.foo") is Foo
    assert registry.all() == {"custom.foo": Foo}
    assert registry.all(family="worldquant") == {}


def test_registry_rejects_duplicate_names():
    registry = AlphaRegistry()

    class A(Alpha):
        name = "dup"
        family = "custom"

        def compute(self, panel):
            return panel.close

    class B(Alpha):
        name = "dup"
        family = "custom"

        def compute(self, panel):
            return panel.close

    registry.register(A)
    with pytest.raises(ValueError):
        registry.register(B)


def test_registry_reregistering_same_class_is_a_noop():
    registry = AlphaRegistry()

    class A(Alpha):
        name = "same"
        family = "custom"

        def compute(self, panel):
            return panel.close

    registry.register(A)
    registry.register(A)  # 不应该报错
    assert registry.get("custom.same") is A


def test_register_alpha_decorator_bare_and_with_name():
    @register_alpha
    class Bare(Alpha):
        name = "bare_alpha"
        family = "custom"

        def compute(self, panel):
            return panel.close

    @register_alpha(name="renamed_alpha")
    class Renamed(Alpha):
        family = "custom"

        def compute(self, panel):
            return panel.close

    assert Bare().qualified_name == "custom.bare_alpha"
    assert Renamed().qualified_name == "custom.renamed_alpha"


def test_custom_alpha_decorator_functional_style():
    @custom_alpha("double_close", min_lookback=1)
    def double_close(panel):
        return panel.close * 2

    instance = double_close()
    assert isinstance(instance, CustomAlpha)
    assert instance.qualified_name == "custom.double_close"
    assert instance.min_lookback == 1

    panel = make_panel(n=5)
    pd.testing.assert_frame_equal(instance.compute(panel), panel.close * 2)
