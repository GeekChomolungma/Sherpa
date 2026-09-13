import pytest

from sherpa.strategy.base import BaseStrategy


def test_strategy_id_defaults_to_class_name():
    class MyStrategy(BaseStrategy):
        def on_bar(self, event, features):
            return None

    strategy = MyStrategy()
    assert strategy.strategy_id == "MyStrategy"


def test_strategy_id_can_be_overridden():
    class MyStrategy(BaseStrategy):
        strategy_id = "custom_id"

        def on_bar(self, event, features):
            return None

    assert MyStrategy().strategy_id == "custom_id"


def test_params_are_stored():
    class MyStrategy(BaseStrategy):
        def on_bar(self, event, features):
            return None

    strategy = MyStrategy(threshold=0.1)
    assert strategy.params == {"threshold": 0.1}


def test_setup_default_is_noop():
    class MyStrategy(BaseStrategy):
        def on_bar(self, event, features):
            return None

    MyStrategy().setup()  # 不应该抛异常


def test_on_bar_not_implemented_by_default():
    strategy = BaseStrategy()
    with pytest.raises(NotImplementedError):
        strategy.on_bar(event=None, features=None)
