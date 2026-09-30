"""关卡1（因子相关性分析与正交化）的参数。

候选因子池不在这里：它来自研究线上一阶段的标准交接文件（`<研究线>/handoff/report.json`，汇总报告
按 04/05 矩阵的显著 + |IC_IR| Top-K 产出），见 `research/_shared/handoff.py`。想手动增删某条研究线的候选
因子，直接改那份交接文件，再从关卡1 开始重跑这条研究线即可。

因子名一律是 registry 的 qualified_name（`"{family}.{name}"`），worldquant / tradingview / custom 三大家族
都能混用；研究线 `track.json` 的 `alphas.modules` 会在运行时 import，触发注册。
"""

from __future__ import annotations

# 两个因子在某个 state 切片内的截面相关均值 |corr_mean| 达到这个阈值，就判定它们在这个 state
# 下冗余——四大关卡·关卡1 的核心判据。0.7 是常见的经验起点，不是理论最优值：具体项目应该
# 结合 `results/orthogonalization/01_regime_factor_correlation_pairs.csv` 里实际的相关性分布去调整。
CORRELATION_THRESHOLD: float = 0.7

# 大盘锚点（regime 打标 + Beta 暴露）不在这里配置：统一来自 `research/research_config.json` 的
# `market.benchmark_symbol`，由 `data.py` 读成 `BENCHMARK_SYMBOL`，保证跟阶段一体检用的是同一个锚点。

# 跟 `regime_factor_report.py` 同一套 low-sample 保护红线：某个 (dimension, state) 切片
# 的样本数太少时，聚类结果/代表因子选择可能只是噪音，输出里会把对应行标记为 low_sample，
# 而不是自动改动或剔除它——保留原结果 + 显式风险标记，跟阶段一体检的处理方式一致。
LOW_SAMPLE_MIN_SAMPLES: int = 100
LOW_SAMPLE_MIN_FRACTION: float = 0.10
