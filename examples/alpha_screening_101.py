"""示例：用 `sherpa.backtest.screening` 批量评估世坤101因子库。

演示"我有一整个因子库，哪些真的有预测力"这个研究场景怎么一步做完：

    registry.all(family="worldquant")  -> 101 个已注册的 Alpha 类
                                        -> AlphaEngine
                                        -> screen_alphas(engine, panel, forward_returns)
                                        -> 按 IC_IR 排序的报告 + 算不出来的因子列表

不需要写策略类、不用 Runner——这条工作流跟 examples/vectorized_research.py 一样完全独立于
sherpa.strategy，只是把"评估一个因子"换成了"批量评估一整个因子库"，这正是
`sherpa.backtest.screening.screen_alphas` 存在的意义：加新因子的时候不用一个个手动调
`run_alpha_check`，一次跑全部、看排行榜就行。

数据是合成的、没有针对任何一条具体公式调过参数（对比 vectorized_research.py 里专门为一个
动量因子调出的强信号合成数据）——所以大部分因子大概率通不过第一层检验，这是正常且符合
预期的结果：101 个公式里能在任意一份具体数据上表现出真实预测力的从来就是少数，这正是
alpha_check 存在的意义（一票否决，筛掉的因子不会被误当成能用的信号）。这个示例的重点是
"批量筛选这条工作流怎么跑通"，不是"证明这批因子有多好"。

运行：
    python examples/alpha_screening_101.py
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import sherpa.alpha.worldquant  # noqa: F401  import 触发 @register_alpha，把 101 个 alpha 都注册进 registry
from sherpa.alpha import registry
from sherpa.alpha.engine import AlphaEngine
from sherpa.backtest.screening import screen_alphas

from _synthetic_market import make_full_synthetic_panel

N_QUANTILES = 5
IC_IR_THRESHOLD = 0.15
TOP_N = 10


def main() -> None:
    panel = make_full_synthetic_panel(n_symbols=15, n_bars=250, seed=0)
    forward_returns = panel.close.pct_change().shift(-1)

    worldquant_alphas = [cls() for cls in registry.all(family="worldquant").values()]
    print(
        f"跑 {len(worldquant_alphas)} 个因子 x {panel.close.shape[1]} 个 symbol x "
        f"{panel.close.shape[0]} 根 bar，世坤101里不少公式是 ts_rank/decay_linear 这类逐窗口"
        "跑 Python 回调的算子，批量跑一遍大概要 20~30 秒，不是卡住。"
    )
    print(f"registry 里共有 {len(worldquant_alphas)} 个已注册的 worldquant alpha")

    engine = AlphaEngine(worldquant_alphas)
    report = screen_alphas(
        engine, panel, forward_returns, n_quantiles=N_QUANTILES, ic_ir_threshold=IC_IR_THRESHOLD
    )

    print(f"\n算不出来的因子（占位，缺 BarPanel 不支持的字段——行业分类/市值）：{len(report.errors)} 个")
    for name in sorted(report.errors):
        print(f"  {name}")

    passed = report.table[report.table["passed"]]
    print(f"\n能算出结果的因子：{len(report.table)} 个，其中通过第一层检验（IC_IR >= {IC_IR_THRESHOLD}"
          f" 且分位数单调）：{len(passed)} 个")

    print(f"\n== IC_IR 排名前 {TOP_N}（最靠前不代表最能赚钱，只代表在这份合成数据上排序最稳定）==")
    print(report.table.head(TOP_N).to_string())

    print(f"\n== IC_IR 排名后 {TOP_N} ==")
    print(report.table.tail(TOP_N).to_string())

    if len(passed):
        print("\n通过第一层检验的因子，建议下一步用 sherpa.backtest.vectorized 或")
        print("sherpa.backtest.alpha_check 单独再细看一遍分位数分组收益，不要只看 IC_IR 一个数字。")


if __name__ == "__main__":
    main()
