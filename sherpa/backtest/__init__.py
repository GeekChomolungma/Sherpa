"""编排层（设计文档 §8.4）：组合调用 `sherpa.metrics` + `sherpa.portfolio`，落地
`docs/backtest_principle.md` 的两层回测体系。

不 import `sherpa.strategy` 的任何东西——依赖方向严格是 `strategy -> backtest`，不允许
反过来（设计文档 §8.4.4 决策1），保证这个包能被研究脚本完全独立于 `Runner`/`BaseStrategy`
调用。
"""
