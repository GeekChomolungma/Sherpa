"""探索实验（research/ml_training/）跟正式关卡3（research/friction_test/）的评估口径必须一致：同一套组合网格、成本、
稳健性过滤。两边各维护一份拷贝（research 子项目之间不互相 import），这里逐项比对，防止某一边改了另一边没跟上。

两个目录都有 config.py / data.py，按文件路径加载、各起一个不重名的模块名。
"""

import importlib.util
import sys
import types
from pathlib import Path

RESEARCH = Path(__file__).resolve().parents[2] / "research"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _friction_config():
    # friction_test/config.py 里 `from data import 费率常量`；它的 data.py 要连数据库，这里换成只带常量的替身
    import json

    costs = json.loads((RESEARCH / "research_config.json").read_text(encoding="utf-8"))["costs"]
    stub = types.ModuleType("data")
    stub.MAKER_FEE_BPS = float(costs["maker_fee_bps"])
    stub.TAKER_FEE_BPS = float(costs["taker_fee_bps"])
    stub.TAKER_SLIPPAGE_BPS = float(costs["taker_slippage_bps"])
    stub.STRESS_SLIPPAGE_BPS = float(costs["stress_slippage_bps"])
    saved = sys.modules.get("data")
    sys.modules["data"] = stub
    try:
        return _load(RESEARCH / "friction_test" / "config.py", "_friction_config_for_alignment")
    finally:
        if saved is None:
            sys.modules.pop("data", None)
        else:
            sys.modules["data"] = saved


def test_exploration_grid_costs_and_filter_match_gate3():
    gate3 = _friction_config()
    explore = _load(RESEARCH / "ml_training" / "evaluation.py", "_ml_evaluation_for_alignment")
    assert explore.WEIGHTINGS == gate3.WEIGHTINGS
    assert explore.REBALANCE_EVERY == gate3.REBALANCE_EVERY
    assert explore.BASE_COST == gate3.BASE_COST
    assert explore.ROBUSTNESS_MAX_FLAT == gate3.ROBUSTNESS_MAX_FLAT
    assert set(explore.COST_MODELS) == set(gate3.COST_MODELS)
    for name, model in gate3.COST_MODELS.items():
        assert vars(explore.COST_MODELS[name]) == vars(model), name
