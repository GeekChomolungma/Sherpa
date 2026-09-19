> **Language:** [English](README.md) | 简体中文

# Sherpa

Sherpa 是一个面向 crypto 量化研究的 **Data-to-Signal 引擎**：把 ClickHouse/Redis 里的行情数据转换成标准化的交易信号（`SignalIntent`），回测和实盘复用同一套策略代码。目标是逐步长成一个完整的**回测研究 + 实盘信号策略库**——目前还没做到，具体差多少见下面的[项目现状](#项目现状)。

下单、仓位对齐、资金清算不在本仓库范围内，那是下游执行服务（"Webhooker"）的职责。Sherpa 到"生成信号"为止。

## 目前有什么

| 层 | 包 | 职责 |
| :-- | :-- | :-- |
| 数据 | `sherpa.data` | `BarPanel`/`MarketEvent` 契约、ClickHouse/Redis 读取器、回测和实盘共用的 `IPanelSource` 抽象 |
| 因子 | `sherpa.alpha` | `Alpha` 基类、`AlphaEngine`，三大家族：世坤101（101/101 全部实现）、TradingView、自定义 |
| 共享工具 | `sherpa.portfolio`、`sherpa.metrics` | 纯函数：alpha→权重映射、换手率、RankIC/IC_IR、Sharpe/Calmar/MaxDrawdown——研究、回测、未来实盘都能复用 |
| 回测 | `sherpa.backtest` | 两层评估体系（见 `docs/backtest_principle.md`）：`alpha_check`/`screening`（统计检验）和 `vectorized`/`event_driven`（带成本的仓位模拟） |
| 策略 | `sherpa.strategy` | `BaseStrategy`、`Runner`（回测和实盘共用同一个主循环）、`sink/` 适配器（`LogSink`/`BacktestSink`/`WebhookSink`） |
| 实盘 | `sherpa.live` | 派发前的格式化（幂等 key、时间戳），不含任何决策逻辑 |

完整设计文档：[`docs/SHERPA_DESIGN.md`](docs/SHERPA_DESIGN.md)；上游数据契约：[`docs/DATA_CONSUMER_GUIDE.md`](docs/DATA_CONSUMER_GUIDE.md)。

## 目录结构

```text
sherpa/       库代码（见上表）
tests/        单元测试，跟 sherpa/ 结构对应
examples/     可直接运行的教学示例（合成数据）
research/     接真实 ClickHouse 数据的研究项目
  alpha_research/          阶段一（单因子挖掘与体检）各因子家族的研究产线
    worldquant_101/          世坤101因子库的批量筛选 + 分类别向量化回测
  tradability_calibration/  sherpa.metrics.tradability.tradable_mask 的超参数校准
  regime_factor_report/     把任意家族的 regime 条件 IC 画像转成人类可读报告
  factor_orthogonalization/ 四大关卡·关卡1：按 regime 切片的相关性聚类/正交化
docs/         设计文档
scripts/      一次性运维脚本（比如 ClickHouse/Redis 连通性烟雾测试）
```

## 快速开始

```bash
pip install -e ".[dev]"
pytest                              # 跑测试
python examples/vectorized_research.py   # 一个基于合成数据的独立示例
```

`research/` 下的脚本需要真实 ClickHouse 连接，用环境变量配置（`CH_HOST`/`CH_PORT`/`CH_USER`/`CH_PASSWORD`/`CH_DATABASE`）——具体看每个脚本开头的说明。

## 项目现状

这是一个能跑通的框架，不是成品。如实说明目前的进度：

- **数据层**——完成，接真实 ClickHouse/Redis 跑过烟雾测试。
- **因子库**——世坤101 的 101 个公式全部实现并注册（其中 19 个是有意的占位：需要 `BarPanel` 目前没有的行业分类/市值数据）。TradingView 目前只有 **2** 个指标。101 个因子里的大多数**还没有**在真实行情数据上验证过——这部分工作在 `research/alpha_research/worldquant_101/` 里，正在做，没做完。
- **回测引擎**——两层流程（`alpha_check`/`screening` → `vectorized`/`event_driven`）能跑通、有单元测试，但围绕它的*研究工作流*（多因子组合、参数敏感性分析、标准化报告）还很薄——现在是"自己调函数"，不是一个打磨过的工具。
- **策略/Runner/sink**——`BaseStrategy`、`Runner`、`LogSink`、`BacktestSink` 都已实现，在 `examples/` 里跑通过端到端流程。但"用验证过的因子搭一个真实策略、走完整回测→sink流程"这件事还没做过。
- **实盘信号路径**——`WebhookSink` 是占位，调用就报错，还没有真正对接执行服务。仓位再平衡/风控这类逻辑目前刻意没有设计——原因见 `docs/SHERPA_DESIGN.md` 第8节。

一句话总结：底层管线搭得比较扎实，因子研究刚起步，实盘这条路径还完全没有。

## License

还没定。
