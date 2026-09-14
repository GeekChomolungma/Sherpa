"""实盘专属、且不改变策略决策结果的"派发前处理"（设计文档 §8.5）。

跟 `sherpa.portfolio`/`sherpa.metrics` 的边界不同：那两个包的函数改变的是数字本身
（权重、绩效指标），会影响策略在任何驱动方式下的实际表现；`sherpa.live` 只处理"已经
决定好的信号要怎么打包成可派发的形状"（幂等 key、派发时间戳等），不改变 `target_percent`
这些决策数字，所以只有 `LogSink`/`WebhookSink` 需要它，`BacktestSink`/`Simulator`
不需要、也不应该依赖它——见设计文档 §8.5 的详细论证。
"""

from .request import LiveOrderRequest, build_live_requests

__all__ = ["LiveOrderRequest", "build_live_requests"]
