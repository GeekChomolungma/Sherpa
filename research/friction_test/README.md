# Friction Test：三大工程关卡 · 关卡3（换手摩擦与组合构建）

对应 [`QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md`](../../QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md) §4「关卡 3：第二层可变现性与资金容量压力测试」。

## 1. 这一关要回答什么

关卡2 比较的是合成分数的**排序能力**（IC）。这一关回答两个问题：

> 这些分数变成真实持仓、扣掉手续费和滑点之后，还能剩下多少收益？
> 用什么方式把分数变成仓位最划算？

关卡3 跟阶段二用的是同一套回测代码（`sherpa.backtest.vectorized`），区别在于**用哪段数据、做什么**：

| | 关卡3（本目录） | 阶段二 |
|---|---|---|
| 数据段 | 研究段：选择段只作参考，**验证段用来比较** | holdout，只跑一次 |
| 做什么 | 在多个 case × 权重映射 × 调仓频率 × 成本假设的组合里比较、挑选 | 冻结整份配方，只做验证，不调参 |
| 结果不好时 | 回到关卡2 或关卡3 修改 | 如实记录 |

## 2. 输入：关卡2 冻结下来的配方

`refresh_candidates.py` 读取关卡2 的两份结果，重写 `config.py` 里的 `CASES` 区块：

- `factor_synthesis/results/01_scheme_comparison.csv`：决定收录哪些方案。默认收录**全部**合成方案，再加 1 个在**选择段**上 IC_IR 最高的单因子作参照；
- `factor_synthesis/results/03_factor_weights.csv`：配方本身，包括每个方案 / 每个 state 用哪些因子、方向和权重。这些都是关卡2 在选择段上估出来的，关卡3 **不重新估计**。

为什么不只收关卡2 的最优方案：几个方案的 IC_IR 往往只差零点零几，但分数稳定性（换手）差得更多，扣完成本后排名可能翻过来。

`run_friction.py` 会先按关卡2 的同一口径重算每个 case 在验证段上的 IC_IR，跟关卡2 报告的数字对照（`00_case_consistency.csv`）。对不上就说明配方重建或数据口径有偏差，后面的回测结论不可信。

## 3. 测试网格（`config.py` 区块外，手动维护）

每个 case 都跑满 `WEIGHTINGS × REBALANCE_EVERY`，每组回测再按 `COST_MODELS` 各扣一次费。

| 维度 | 当前取值 | 说明 |
|---|---|---|
| `WEIGHTINGS`：分数 → 仓位 | Top-K 多空 + 排名迟滞：`top10` / `top10_exit20` / `_exit30` / `_exit50`，`top20` / `top20_exit40` / `_exit60` / `_exit100` | 做多分数最高的 k 个、做空最低的 k 个，各等权，总敞口统一为 1（多空各 0.5）。`exit_k`：排进前 k 才开仓，跌出前 exit_k 才平仓（`sherpa.portfolio.buffer.top_k_hysteresis`），`exit_k = k` 就是不设缓冲 |
| `REBALANCE_EVERY`：调仓频率 | 1 / 3 / 6 根 bar（4h 周期下是每 4 小时 / 12 小时 / 1 天） | 每 N 根 bar 把整个组合换成最新目标（全仓调仓），中间不交易，持仓随价格漂移 |
| `COST_MODELS`：成本 | `zero` / `all_maker` / `all_taker` / `stress` | 费率读自 `research_config.json` 的 `costs` 一节，换会员档位或交易所只改 JSON。挂单能成交多少事先估不出来，所以只跑两个极端：`all_maker` 是全部挂单、不计滑点（乐观上限）；`all_taker` 是全部吃单加常规滑点（保守）。`stress` 是吃单加大滑点，`zero` 用来算毛收益 |
| 验收红线 | `all_taker` 成本下、验证段：净 Sharpe ≥ 2.5 且换手衰减 < 40% | 取自 lifecycle 文档 §4 关卡3 |

执行时点跟 IC 标签对齐：`shift = 1 + execution_delay_bars`。信号在 t 收盘算出，t+delay 收盘成交，回测赚的正是 IC 标签衡量的那段收益。

## 4. 标签持有期（`label.horizon_bars`）

`research_config.json` 的 `label.horizon_bars = H` 决定阶段一**按多长的持有期**给因子打分：t 行的标签是 `close[t+delay] → close[t+delay+H]` 的收益。`H > 1` 时相邻标签重叠，IC 序列天然带 H−1 阶自相关，显著性检验的 Newey–West 滞后阶数会自动加到至少 `2(H−1)`（`sherpa.metrics.factor.overlap_min_lags`）。

**比较不同 H 的 IC_IR 时要先折算成年化**：每根 bar 算一次的 IC_IR 在 H 变大时会"虚高"，因为每年独立下注的次数只有 1/H。可比的量是 `IC_IR × √(每年 bar 数 / H)`。

2026-09 试过 H=6（见 §7）：IC_IR 从约 0.32 升到约 0.49，折算成年化后反而从约 15 降到约 9.4，关卡3 的毛 Sharpe 也更低。结论是：当前因子库的预测力集中在前一两根 bar，**改标签口径筛不出本来不存在的慢信号**，要找慢信号得换因子家族。当前配置已改回 H=1。

## 5. 运行

```bash
# 关卡2 跑完之后：
python refresh_candidates.py                  # 关卡2 results -> config.CASES
CH_HOST=... CH_PASSWORD=... python run_friction.py

# 或者用一键脚本（步骤 10 刷新 case，步骤 11 回测）：
bash run_research.sh --from-step 10 --refresh-friction-cases
```

`refresh_candidates.py --max-composites N` 只保留验证段 IC_IR 前 N 个合成方案；`--singles N` 设置单因子参照的个数。回测按 case 分到多个进程并行（`run_friction.MAX_WORKERS`）。

## 6. 产出（`results/`）与阅读顺序

1. **`00_case_consistency.csv`**：先确认 `consistent` 全部是 True。
2. **`02_validation_base_cost.csv`**：验证段、`all_taker` 成本下，每种 (case, 映射, 调仓频率) 一行，按净 Sharpe 排序。重点看这几列：
   - `gross_sharpe` → `net_sharpe[all_maker]` → `net_sharpe`（all_taker）→ `net_sharpe[stress]`：零成本、两种极端执行方式、大滑点下 Sharpe 各剩多少；
   - `turnover_per_bar`、`turnover_decay`：换手有多高，成本吃掉了毛利的多大比例；
   - `breakeven_cost_bps`：单边成本涨到多少 bps 时净收益归零。直接拿它跟 maker / taker 费率比较，最直观；
   - `passes_red_lines`：是否满足验收红线。
3. **`01_friction_summary.csv`**：完整长表，包含所有成本假设和选择段。用来确认结论不是只在验证段上成立。
4. **`03_validation_net_equity.csv`**：验证段净 Sharpe 前 30 名组合的净值曲线（宽表），用来画图、看回撤出现在什么时候。

**关于网格搜索的偏差**：在验证段上从几百种组合里挑最高的那一格，结果天然偏乐观。要看**稳健的区域**（相邻参数都不错），比如按映射 × 调仓频率看 8 个 case 的中位数，不要只看单独最好的一格。无偏的估计留给阶段二在 holdout 上跑。

## 7. 已经试过、已排除的做法

以下结论来自 2026-09 的五轮网格（除特别注明外都是 `horizon_bars = 1` 的因子池），看验证段、8 个 case 的中位数。以后因子池或标签变了，可以再打开重测。

| 做法 | 结果 | 结论 |
|---|---|---|
| 按分数配权（`demean_l1`） | 全币池持仓，换手高；taker 成本下净 Sharpe 中位数在 -2 ～ -5 | 不如 Top-K，已移出网格 |
| `demean_l1` + 逐币不交易带（`no_trade_band`，band 0.001～0.004） | band 取到大于单币平均权重时，换手也只从 0.61 降到 0.45 | 几百个币的权重每期都在整体变化，逐币冻结解决不了。函数保留在 `sherpa.portfolio.buffer` |
| 合成分数 EMA 平滑（半衰期 1～4 根 bar） | 换手降了，但毛收益掉得更快：top10 逐 bar 调仓，毛 Sharpe 从 1.77 降到 1.46（半衰期 1）、0.35（半衰期 4） | 预测力只在最新一根 bar 上，平滑等于在用过期信号，已移出网格 |
| Top-40 | 同样的迟滞倍数下普遍不如 top10 / top20；`top40_exit160` 几乎是买入持有，毛收益约为 0 | 已移出网格 |
| 分批持仓（资金分 H 份，每根 bar 只调其中一份，每份持有 H 根） | 换手跟同持有期的全仓调仓（`everyN`）几乎相同；H=1 时叠加迟滞后不如 `everyN`；H=6 时 `tranches6` 也没有比 `every6` 更好——每一份都拿着逐渐过期的信号 | 当前信号下没有收益，实现已删除，只保留全仓调仓 |
| 标签持有期 H=6（整条链重跑） | 阶段一候选池 11 个里 9 个跟 H=1 相同；关卡2 验证段 IC_IR 约 0.49，但年化折算后约 9.4，低于 H=1 的约 15；关卡3 验证段毛 Sharpe 中位数 1.0～1.7（H=1 时 1.4～1.9），taker 成本下全部为负 | 已改回 H=1，见 §4 |
| Top-K 排名迟滞 | **有效**：top20 → top20_exit60，逐 bar 调仓的换手从 0.86 降到 0.32，毛 Sharpe 从 1.65 降到 1.44 | 保留。去掉的是边界附近来回进出的无效交易 |

当时的整体结论：迟滞之后，保本成本在 8～15 bps，taker 成本下最好的组合净 Sharpe 约 1.0；零成本的毛 Sharpe 最高也只有约 2.2，**红线 2.5 靠组合构建达不到，瓶颈在信号本身**（持有期太短）。改标签持有期也解决不了（§4），下一步是换因子家族。

## 8. 尚未覆盖（后续）

- **资金费率**：永续合约持仓要付或收资金费，目前缺数据，还没建模；
- **容量**：没有按成交额估算冲击成本和参与率。需要回测输出逐 symbol 的交易额，再配合 `quote_volume`；
- **挂单成交率**：目前只跑了全 maker 和全 taker 两个极端，真实结果在两者之间。等有了实盘或模拟盘的成交数据，再把实际成交率折算进成本；
- **事件驱动交叉验证**：最终选定的组合应该在 `sherpa.backtest.event_driven` 上复跑一次，核对逐期收益一致。
