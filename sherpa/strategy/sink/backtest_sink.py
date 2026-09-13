"""`BacktestSink`：回测用 sink，接入内部撮合模拟（设计文档 §8/§9）。

尚未实现——它依赖第8章的撮合逻辑（订单只能在 `event.bar_end_time` 之后成交，需要维护
持仓/资金状态才能算出收益率、Sharpe、MaxDrawdown 等指标），这些还没有设计落地。这个占位
类是给 `Runner.run_backtest` 一个明确的失败方式和统一接入点，不要为了"能跑"就在这里塞一个
只记账不撮合的简化版本——那样产出的回测指标没有意义，比不实现更容易误导人。

在撮合引擎落地之前，`run_backtest` 可以先接 `LogSink`，只验证 Pipeline 主循环本身
（panel_source -> alpha_engine -> strategy -> sink 这条链路）跑得通，不代表回测结果可信。
"""

from __future__ import annotations

from typing import Sequence

from ..schema import SignalIntent


class BacktestSink:
    def submit(self, intents: Sequence[SignalIntent]) -> None:
        raise NotImplementedError("BacktestSink 依赖第8章的撮合引擎，尚未实现（设计文档 §8/§9）")
