"""关卡3（换手摩擦与组合构建测试）的配置。

分两部分：

1. **`CASES`：要回测的"冻结配方"**，由 `refresh_candidates.py` 从关卡2 的产出自动重写（BEGIN/END 之间）。
   每个 case 是一套完整的合成规则——用哪些因子、方向、权重、是否按 regime 路由——直接取自关卡2
   `factor_synthesis/results/03_factor_weights.csv`（关卡2 在选择段上估出的方向 / 权重），不在关卡3 重估。
   默认收录关卡2 的**全部**合成方案，再加选择段最强的单因子作参照：关卡2 只看 IC，IC 相近的方案扣费后
   排名完全可能翻转，所以不在这一关之前就只留一个。想手动删减 / 增加 case，直接改区块里的内容即可，
   但下次跑 `refresh_candidates.py` 时这一块会被整块覆盖。

2. **组合构建网格与成本假设**（区块外，手动维护）：`WEIGHTINGS`（Top-K + 排名迟滞）× `REBALANCE_EVERY`（调仓频率）
   每种组合都对每个 case 跑一遍回测，再在 `COST_MODELS` 的每种成本假设下各算一套扣费绩效。费率读自
   `research_config.json` 的 `costs` 一节。

case 的格式：

    "G0 全局等权": {"kind": "static", "weights": {qualified_name: 带符号权重, ...}}
    "L2-volatility 路由等权": {
        "kind": "routed", "dimension": "volatility",
        "states": {state: {qualified_name: 带符号权重, ...}, ...},
        "fallback": {qualified_name: 带符号权重, ...},   # state 未知 / 没有配方时用（关卡2 用的是 L0）
    }

权重带符号：符号 = 方向，绝对值 = 权重大小（`signals.weighted_composite` 会按 Σ|w| 归一）。
"""

from __future__ import annotations

from typing import Any

from sherpa.backtest.cost_model import CostModel, FixedFeeCostModel, ZeroCostModel

from data import MAKER_FEE_BPS, STRESS_SLIPPAGE_BPS, TAKER_FEE_BPS, TAKER_SLIPPAGE_BPS

# >>> CASES BEGIN
CASES: dict[str, dict[str, Any]] = {
    # 关卡2：验证段 IC_IR=+0.326，选择段 IC_IR=+0.259，验证段 score_autocorr=0.764
    'L2-volatility 路由等权': {
        'kind': 'routed',
        'dimension': 'volatility',
        'states': {
            'high': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha029': 1.0,
            },
            'normal': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha025': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha044': 1.0,
            },
            'low': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha055': 1.0,
            },
        },
        'fallback': {
            'worldquant.alpha040': 1.0,
            'worldquant.alpha094': 1.0,
            'worldquant.alpha036': 1.0,
            'worldquant.alpha044': 1.0,
            'worldquant.alpha077': 1.0,
            'worldquant.alpha016': 1.0,
            'worldquant.alpha029': 1.0,
            'worldquant.alpha025': 1.0,
            'worldquant.alpha055': 1.0,
            'worldquant.alpha050': 1.0,
            'worldquant.alpha015': 1.0,
            'worldquant.alpha037': 1.0,
            'worldquant.alpha073': 1.0,
        },
    },
    # 关卡2：验证段 IC_IR=+0.321，选择段 IC_IR=+0.254，验证段 score_autocorr=0.708
    'L2-trend 路由等权': {
        'kind': 'routed',
        'dimension': 'trend',
        'states': {
            'bull': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha036': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha077': 1.0,
            },
            'bear': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha029': 1.0,
            },
            'neutral': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha025': 1.0,
            },
        },
        'fallback': {
            'worldquant.alpha040': 1.0,
            'worldquant.alpha094': 1.0,
            'worldquant.alpha036': 1.0,
            'worldquant.alpha044': 1.0,
            'worldquant.alpha077': 1.0,
            'worldquant.alpha016': 1.0,
            'worldquant.alpha029': 1.0,
            'worldquant.alpha025': 1.0,
            'worldquant.alpha055': 1.0,
            'worldquant.alpha050': 1.0,
            'worldquant.alpha015': 1.0,
            'worldquant.alpha037': 1.0,
            'worldquant.alpha073': 1.0,
        },
    },
    # 关卡2：验证段 IC_IR=+0.319，选择段 IC_IR=+0.248，验证段 score_autocorr=0.808
    'L1 全局ICIR加权': {
        'kind': 'static',
        'weights': {
            'worldquant.alpha040': 0.2209336582227068,
            'worldquant.alpha094': 0.1786683463002915,
            'worldquant.alpha016': 0.1715250600551104,
            'worldquant.alpha044': 0.1629059271777197,
            'worldquant.alpha029': 0.138624699758571,
        },
    },
    # 关卡2：验证段 IC_IR=+0.315，选择段 IC_IR=+0.259，验证段 score_autocorr=0.688
    'L2-liquidity 路由等权': {
        'kind': 'routed',
        'dimension': 'liquidity',
        'states': {
            'high': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha055': 1.0,
                'worldquant.alpha025': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha037': 1.0,
            },
            'normal': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha029': 1.0,
            },
            'starved': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha073': 1.0,
            },
        },
        'fallback': {
            'worldquant.alpha040': 1.0,
            'worldquant.alpha094': 1.0,
            'worldquant.alpha036': 1.0,
            'worldquant.alpha044': 1.0,
            'worldquant.alpha077': 1.0,
            'worldquant.alpha016': 1.0,
            'worldquant.alpha029': 1.0,
            'worldquant.alpha025': 1.0,
            'worldquant.alpha055': 1.0,
            'worldquant.alpha050': 1.0,
            'worldquant.alpha015': 1.0,
            'worldquant.alpha037': 1.0,
            'worldquant.alpha073': 1.0,
        },
    },
    # 关卡2：验证段 IC_IR=+0.314，选择段 IC_IR=+0.261，验证段 score_autocorr=0.760
    'L0 并集等权': {
        'kind': 'static',
        'weights': {
            'worldquant.alpha040': 1.0,
            'worldquant.alpha094': 1.0,
            'worldquant.alpha036': 1.0,
            'worldquant.alpha044': 1.0,
            'worldquant.alpha077': 1.0,
            'worldquant.alpha016': 1.0,
            'worldquant.alpha029': 1.0,
            'worldquant.alpha025': 1.0,
            'worldquant.alpha055': 1.0,
            'worldquant.alpha050': 1.0,
            'worldquant.alpha015': 1.0,
            'worldquant.alpha037': 1.0,
            'worldquant.alpha073': 1.0,
        },
    },
    # 关卡2：验证段 IC_IR=+0.313，选择段 IC_IR=+0.254，验证段 score_autocorr=0.782
    'L2-dispersion 路由等权': {
        'kind': 'routed',
        'dimension': 'dispersion',
        'states': {
            'high': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha029': 1.0,
                'worldquant.alpha044': 1.0,
            },
            'normal': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha050': 1.0,
            },
            'low': {
                'worldquant.alpha040': 1.0,
                'worldquant.alpha044': 1.0,
                'worldquant.alpha094': 1.0,
                'worldquant.alpha016': 1.0,
                'worldquant.alpha015': 1.0,
            },
        },
        'fallback': {
            'worldquant.alpha040': 1.0,
            'worldquant.alpha094': 1.0,
            'worldquant.alpha036': 1.0,
            'worldquant.alpha044': 1.0,
            'worldquant.alpha077': 1.0,
            'worldquant.alpha016': 1.0,
            'worldquant.alpha029': 1.0,
            'worldquant.alpha025': 1.0,
            'worldquant.alpha055': 1.0,
            'worldquant.alpha050': 1.0,
            'worldquant.alpha015': 1.0,
            'worldquant.alpha037': 1.0,
            'worldquant.alpha073': 1.0,
        },
    },
    # 关卡2：验证段 IC_IR=+0.312，选择段 IC_IR=+0.241，验证段 score_autocorr=0.795
    'G0 全局等权': {
        'kind': 'static',
        'weights': {
            'worldquant.alpha040': 1.0,
            'worldquant.alpha094': 1.0,
            'worldquant.alpha016': 1.0,
            'worldquant.alpha044': 1.0,
            'worldquant.alpha029': 1.0,
        },
    },
    # 关卡2：验证段 IC_IR=+0.260，选择段 IC_IR=+0.221，验证段 score_autocorr=0.861（单因子参照，按选择段 IC_IR 挑选）
    'single:worldquant.alpha040': {
        'kind': 'static',
        'weights': {
            'worldquant.alpha040': 1.0,
        },
    },
}
# <<< CASES END


# ---------------------------------------------------------------------------
# 组合构建网格（run_friction.py 用；以下不会被 refresh_candidates.py 改动）
# 前几轮网格的结论（为什么现在只剩这些）见 README「已经试过、已排除的做法」。
# ---------------------------------------------------------------------------

# 分数 → 单份目标权重的映射：Top-K 多空 + 排名迟滞（`sherpa.portfolio.buffer.top_k_hysteresis`）。
# 做多分数最高的 k 个、做空最低的 k 个，各等权，总敞口统一成 1（多空各 0.5，见 `signals.target_path`）；
# 排进前 k 开仓、跌出前 exit_k 才平仓，exit_k == k 就是不设缓冲。有效 symbol 不足 2k 的 bar 空仓。
TOP_K_EXITS: dict[int, tuple[int, ...]] = {10: (10, 20, 30, 50), 20: (20, 40, 60, 100)}

WEIGHTINGS: dict[str, dict[str, Any]] = {
    (f"top{k}" if exit_k == k else f"top{k}_exit{exit_k}"): {"method": "top_k", "k": k, "exit_k": exit_k}
    for k, exits in TOP_K_EXITS.items()
    for exit_k in exits
}

# 每隔几根 bar 全仓调一次仓（研究周期 4h：1 = 每 4 小时，3 = 每 12 小时，6 = 每天）。非调仓 bar 不交易，
# 持仓随价格漂移（`run_vectorized_backtest(rebalance_every=...)`）。调仓越稀疏换手越低，但信号越"旧"。
REBALANCE_EVERY: tuple[int, ...] = (1, 3, 6)

# 成本假设：{名字: CostModel}，按"单边换手 × (手续费 + 滑点)"扣。费率来自 `research_config.json` 的 `costs`
# 一节（换会员档位 / 换交易所只改 JSON）。挂单能成交多少没法事先估计，所以只跑两个极端：
# - all_maker：全部挂单成交、无滑点——乐观上限（没算挂单不成交、逆向选择）；
# - all_taker：全部吃单 + 常规滑点——保守口径，**验收红线按它判定**；
# - stress：全部吃单 + 大滑点，看结论对滑点假设有多敏感；
# - zero：零成本，给出毛收益，用来算换手衰减率。
# 永续合约的资金费率还没有建模（缺数据），见 README「尚未覆盖」。
COST_MODELS: dict[str, CostModel] = {
    "zero": ZeroCostModel(),
    "all_maker": FixedFeeCostModel(fee_bps=MAKER_FEE_BPS, slippage_bps=0.0),
    "all_taker": FixedFeeCostModel(fee_bps=TAKER_FEE_BPS, slippage_bps=TAKER_SLIPPAGE_BPS),
    "stress": FixedFeeCostModel(fee_bps=TAKER_FEE_BPS, slippage_bps=STRESS_SLIPPAGE_BPS),
}
BASE_COST: str = "all_taker"

# 验收红线（QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md §4 关卡3）：在 BASE_COST 下、验证段上判定。
MIN_NET_SHARPE: float = 2.5
MAX_TURNOVER_DECAY: float = 0.40
