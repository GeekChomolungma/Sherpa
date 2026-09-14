"""示例：纯向量化研究——不写策略类，不用 Runner，直接检验一个因子 + 跑向量化回测。

演示设计文档 §8 的研究工作流：

    AlphaEngine.compute_history() -> backtest.alpha_check（第一层，一票否决）
                                   -> backtest.vectorized（第二层，向量化模拟）

全程不接触 sherpa.strategy——评估一个原始 alpha 时根本不存在"策略"这个概念，这也是
设计文档 §8.4.4 决策1 强调"sherpa.backtest 不依赖 sherpa.strategy"的原因：这条工作流
必须能在完全没有 Runner/BaseStrategy 的情况下独立跑起来，适合"我有个新因子想先看看
靠不靠谱"这种场景。

跟 examples/runner_backtest_with_stop_loss.py 对比着看：那个示例里同样的动量因子，是
通过 BaseStrategy.on_bar() + Runner 跑的，因为那个示例还叠加了止损这种路径依赖逻辑，
本示例的 weighting_fn（demean_l1）是纯函数，没有这个需要，向量化路径就够用、且快得多。

运行：
    python examples/vectorized_research.py
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    # Windows 控制台默认代码页常常不是 UTF-8，不重配置的话中文输出会乱码
    # （脚本源码本身是 UTF-8，纯粹是终端显示问题，不影响 Linux/macOS）。
    sys.stdout.reconfigure(encoding="utf-8")

from sherpa.alpha.base import custom_alpha
from sherpa.alpha.engine import AlphaEngine
from sherpa.backtest.alpha_check import run_alpha_check
from sherpa.backtest.cost_model import FixedFeeCostModel
from sherpa.backtest.vectorized import run_vectorized_backtest
from sherpa.portfolio.weighting import demean_l1

from _synthetic_market import close_to_panel, make_synthetic_ohlcv

MOMENTUM_LOOKBACK = 60
ALPHA_NAME = f"custom.momentum_{MOMENTUM_LOOKBACK}"


@custom_alpha(f"momentum_{MOMENTUM_LOOKBACK}", min_lookback=MOMENTUM_LOOKBACK + 1)
def momentum(panel):
    """过去 N 根的累计收益率——最简单的截面动量因子。"""
    return panel.close.pct_change(MOMENTUM_LOOKBACK)


def main() -> None:
    close, _mus = make_synthetic_ohlcv(n_symbols=10, n_bars=500, mu_spread=0.004, noise_std=0.01, seed=0)
    panel = close_to_panel(close)

    engine = AlphaEngine([momentum()])
    alpha_history = engine.compute_history(panel)[ALPHA_NAME]

    # 未来收益率：alpha_t 要跟"t 之后才实现"的收益比，不能跟同一根 bar 的收益比，否则
    # 第一层检验自己就有前视偏差——RankIC 度量的是"预测力"，比较对象必须是真正的未来。
    forward_returns = panel.close.pct_change().shift(-1)

    print("== 第一层：Alpha Check ==")
    check = run_alpha_check(alpha_history, forward_returns, n_quantiles=5, ic_ir_threshold=0.15)
    print(f"IC 均值:  {check.ic_mean:.4f}")
    print(f"IC_IR:    {check.ic_ir:.4f}")
    print(f"通过:     {check.passed}")
    print("分位数分组平均收益（组1=alpha最高 -> 组5=alpha最低，应该逐组递减）：")
    print(check.quantile_returns.mean(axis=0).to_string())

    if not check.passed:
        print("\n因子没有通过第一层检验——正常做法是就此止步，不进入第二层。")
        return

    print("\n== 第二层：向量化 Portfolio & Friction Check ==")
    result = run_vectorized_backtest(alpha_history, panel, demean_l1, FixedFeeCostModel(fee_bps=5))
    print(f"最终净值:     {result.equity_curve.iloc[-1]:.4f}")
    print(f"年化 Sharpe:  {result.sharpe:.2f}（合成数据信噪比远高于真实市场，这个数字不代表真实策略水平）")
    print(f"Calmar:       {result.calmar:.2f}")
    print(f"最大回撤:     {result.max_drawdown:.2%}")
    print(f"平均单期换手: {result.turnover.mean():.2%}")


if __name__ == "__main__":
    main()
