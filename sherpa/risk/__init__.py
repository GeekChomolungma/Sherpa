"""风险与风格暴露：截面中性化回归的自变量计算 + 残差化。

对应 `QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md` 阶段一 · 中性化——原"四大关卡·关卡2：风险与风格
中性化"，经讨论确认这一步必须在阶段一体检阶段就对每个候选因子的原始分数做残差化（先中性化，
再喂给条件 IC 体检和关卡1正交化聚类），否则关卡1的相关性聚类会把"共同的 beta/size 暴露"误判
成"信息冗余"。因此这一步已并入阶段一，不再单独编号为关卡。

跟 `sherpa.metrics`/`sherpa.portfolio` 同一条包级约定：只依赖 pandas/numpy，不 import 仓库
内其他模块（不认识 `BarPanel`、不认识 `sherpa.alpha.Alpha`，哪怕是同样只依赖 pandas/numpy 的
`sherpa.alpha.ops` 也不导入）——保证可以脱离 Sherpa 其余部分单独复用/测试。`BarPanel` 拆包
这一步（取 `panel.close`/`panel.quote_volume` 喂进来）交给调用方做，参考
`sherpa.backtest.regime_screening.regime_report()` 对 `sherpa.metrics.regime` 的适配方式。
"""
