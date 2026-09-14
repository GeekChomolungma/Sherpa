"""alpha -> 目标权重的纯函数映射（设计文档 §8.3）。

策略/回测第二层/未来实盘共用同一套函数，不允许各自实现各自的映射逻辑（见设计文档
§8.3 决策1）。只依赖 pandas/numpy，不 import `sherpa.strategy`/`sherpa.backtest`。
"""
