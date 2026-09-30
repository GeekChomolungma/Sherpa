"""关卡2（基于 Regime 的动态多因子合成）的参数。

候选因子池不在这里：它来自研究线上一阶段的标准交接文件（`<研究线>/handoff/orthogonalization.json`，
关卡1 去冗余后的保留名单；关卡1 透传时就是汇总报告的 Top-K 原样转交），见 `research/_shared/handoff.py`。
名单里的因子已经依次通过了：

1. **阶段一体检**：剥离 Beta/Size 后的残差 IC，在该 state 切片内显著（|t| >= 3）且 |IC_IR| 排名靠前；
2. **关卡1 去冗余**（如果这条研究线跑了关卡1）：在同一个 state 内，和其它候选的截面相关没有高到被判为冗余
   （或者它就是冗余簇里信噪比最高、被选为代表的那个）。

所以关卡2 不再做"选不选这个因子"的判断，只回答"怎么把这些因子合成一个分数"。候选集里的全局名单
（不看 regime 选出、按全历史去冗余）是全局对照组 G0 的候选池；它和各 state 名单经过完全相同的门槛和去冗余，
唯一区别是"选因子时看不看 regime"，所以 G0 与 regime 方案的差距，才能归因到 regime 本身（README §4）。

L2 路由方案按候选集里出现的每个 regime 维度各跑一版（研究线只看 trend 时就只有 L2-trend）。
"""

from __future__ import annotations

from typing import Optional

# 大盘锚点（regime 打标 + Beta 暴露）不在这里配置：统一来自 `research/research_config.json` 的
# `market.benchmark_symbol`，由 `data.py` 读成 `BENCHMARK_SYMBOL`，跟阶段一、关卡1 用的是同一个锚点。

# 估计因子方向（IC 符号）的最少样本数：全局方向 / 按 state 的方向。state 样本不足时退回全局方向。
SIGN_MIN_SAMPLES_GLOBAL: int = 30
SIGN_MIN_SAMPLES_STATE: int = 100

# 交给关卡3 的配方集（`<研究线>/handoff/synthesis.json`）收哪些方案：
# - 合成方案默认全收（按验证段 IC_IR 排序）。关卡2 只比了 IC，几个方案的 IC_IR 往往只差零点零几，而分数稳定性
#   （换手）差别更大——扣完成本排名可能翻转，所以不在进关卡3 之前就砍掉。设成 N 只收验证段 IC_IR 前 N 个；
# - 单因子参照默认收 1 个：**选择段** IC_IR 最高的那个（按验证段挑等于先偷看答案再拿它当对照）。0 = 不要。
HANDOFF_MAX_COMPOSITES: Optional[int] = None
HANDOFF_SINGLES: int = 1
