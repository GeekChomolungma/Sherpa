"""关卡3（换手摩擦与组合构建测试）的参数：组合构建网格与成本假设。

要回测的配方不在这里：它来自研究线上一阶段的标准交接文件（`<研究线>/handoff/synthesis.json`，
见 `research/_shared/handoff.py`）——关卡2 真跑时是它在验证段上比较过的全部合成方案 + 最强单因子参照，
方向 / 权重都是关卡2 在选择段上估好的，不在关卡3 重估；关卡2 透传时是候选集直接变成的等权配方（名字带
`直通·` 前缀）。想手动删减 / 增加配方，直接改那份交接文件，再从关卡3 开始重跑即可。

配方格式（`handoff.validate_recipe`）：

    {"kind": "static", "weights": {qualified_name: 带符号权重, ...}}
    {"kind": "routed", "dimension": "volatility",
     "states": {state: {qualified_name: 带符号权重, ...}, ...},
     "fallback": {qualified_name: 带符号权重, ...}}   # state 未知 / 没有配方时用；空 = 不持仓

权重带符号：符号 = 方向，绝对值 = 权重大小（`signals.weighted_composite` 会按 Σ|w| 归一）。

`WEIGHTINGS`（Top-K + 排名迟滞）× `REBALANCE_EVERY`（调仓频率）每种组合都对每个配方跑一遍回测，再在
`COST_MODELS` 的每种成本假设下各算一套扣费绩效。费率读自 `research_config.json` 的 `costs` 一节。
"""

from __future__ import annotations

from typing import Any

from sherpa.backtest.cost_model import CostModel, FixedFeeCostModel, ZeroCostModel

from data import MAKER_FEE_BPS, STRESS_SLIPPAGE_BPS, TAKER_FEE_BPS, TAKER_SLIPPAGE_BPS

# ---------------------------------------------------------------------------
# 组合构建网格（run_friction.py 用）
# 前几轮网格的结论（为什么现在只剩这些）见 README「已经试过、已排除的做法」。
# ---------------------------------------------------------------------------

# 分数 → 单份目标权重的映射：Top-K 多空 + 排名迟滞（`sherpa.portfolio.buffer.top_k_hysteresis`）。
# 做多分数最高的 k 个、做空最低的 k 个，各等权，总敞口统一成 1（多空各 0.5，见 `signals.target_path`）；
# 排进前 k 开仓、跌出前 exit_k 才平仓，exit_k == k 就是不设缓冲。有效 symbol 不足 2k 的 bar 空仓。
TOP_K_EXITS: dict[int, tuple[int, ...]] = {10: (10, 20, 30, 50), 20: (20, 40, 60, 100)}

# 相对分位版（2026-10-05 起）：k / exit_k 按当期有效 symbol 数的比例算——`q10_exit30` = 排进前 10% 开仓、跌出前 30%
# 才平仓。绝对名次在币池小的早期几乎从不触发平仓、币池大了才正常换手，同一个参数在两段是两种策略；按比例算没有这个漂移。
# 有效 symbol 少于 20 个的期空仓（`sherpa.backtest.score_backtest.target_path` 的 top_quantile）。
TOP_QUANTILE_EXITS: dict[float, tuple[float, ...]] = {0.1: (0.1, 0.2, 0.3), 0.2: (0.2, 0.4)}

WEIGHTINGS: dict[str, dict[str, Any]] = {
    **{
        (f"top{k}" if exit_k == k else f"top{k}_exit{exit_k}"): {"method": "top_k", "k": k, "exit_k": exit_k}
        for k, exits in TOP_K_EXITS.items()
        for exit_k in exits
    },
    **{
        (f"q{round(q * 100)}" if exit_q == q else f"q{round(q * 100)}_exit{round(exit_q * 100)}"):
            {"method": "top_quantile", "q": q, "exit_q": exit_q}
        for q, exits in TOP_QUANTILE_EXITS.items()
        for exit_q in exits
    },
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

# 稳健性汇总（04_robustness.csv）：选择段空仓比例超过这个值的组合不计入中位数——它的 Sharpe 是在很少的交易 bar 上
# 算出来的（比如币池小的时候宽 Top-K 整段空仓），混进来会让中位数失真。
ROBUSTNESS_MAX_FLAT: float = 0.2
MAX_TURNOVER_DECAY: float = 0.40
