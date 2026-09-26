"""关卡2（基于 Regime 的动态多因子合成）的配置。

目前只有**候选因子池**这一项：每个 regime state 下参与合成的因子名单。合成方法本身的参数
（主维度、小样本收缩强度、平滑参数、walk-forward 切分等，见 `README.md` §3~§6）等代码
落地时再加进来。

候选池的来源和含义
------------------
`REGIME_FACTOR_SETS` 来自关卡1 的产出 `factor_orthogonalization/results/02_regime_cluster_assignments.csv`
里被建议保留（`recommendation` 为 keep）的因子，由同目录的 `refresh_candidates.py` 自动重写
（`run_research.sh --refresh-synthesis-candidates` 会调用它）。名单里的因子已经依次通过了：

1. **阶段一体检**：剥离 Beta/Size 后的残差 IC，在该 state 切片内显著（|t| >= 3）且 |IC_IR| 排名靠前；
2. **关卡1 去冗余**：在同一个 state 内，和其它候选的截面相关没有高到被判为冗余（或者它就是
   冗余簇里信噪比最高、被选为代表的那个）。

所以关卡2 不再做"选不选这个因子"的判断，只回答"怎么把这些因子合成一个分数"。

跟 `factor_orthogonalization/config.py` 一样：想手动增删因子，直接改下面 BEGIN/END 之间的
名单即可；但下次带 `--refresh-synthesis-candidates` 跑 `run_research.sh` 时，这一块会被整块覆盖。
"""

from __future__ import annotations

# 12 个 regime 状态各自参与合成的因子：{dimension: {state: [qualified_name, ...]}}。
# 维度名与 state 取值跟 `sherpa.backtest.regime_screening.regime_report()` 的输出一致。
#
# 每个因子行尾的注释（残差 IC_IR、方向、所代表的冗余簇）只是方便人读的快照，代码不解析它们。
# 注意方向（+/-）也只作参考：关卡2 会在每个 walk-forward 训练窗里重新估计方向和权重，
# 不直接沿用这里的符号（README §5.1）。
#
# 下面两行 BEGIN/END 标记之间的内容会被 `refresh_candidates.py` 整块重写。
# >>> REGIME_FACTOR_SETS BEGIN
REGIME_FACTOR_SETS: dict[str, dict[str, list[str]]] = {
    "trend": {
        # trend.bull low_sample=True：样本偏少，关卡2 会把它的权重往全局权重收缩
        "bull": [
            "worldquant.alpha040",  # IC_IR=+0.227
        ],
        "bear": [
            "worldquant.alpha040",  # IC_IR=+0.148
            "worldquant.alpha094",  # IC_IR=+0.114
            "worldquant.alpha044",  # IC_IR=+0.105
            "worldquant.alpha026",  # IC_IR=+0.097
            "worldquant.alpha029",  # IC_IR=+0.096
        ],
        "neutral": [
            "worldquant.alpha040",  # IC_IR=+0.148
            "worldquant.alpha094",  # IC_IR=+0.130
            "worldquant.alpha016",  # IC_IR=+0.119
            "worldquant.alpha039",  # IC_IR=+0.095
            "worldquant.alpha073",  # IC_IR=+0.095
        ],
    },
    "volatility": {
        "high": [
            "worldquant.alpha040",  # IC_IR=+0.133
            "worldquant.alpha094",  # IC_IR=+0.125
            "worldquant.alpha036",  # IC_IR=+0.102
            "worldquant.alpha044",  # IC_IR=+0.101
            "worldquant.alpha055",  # IC_IR=+0.098
        ],
        "normal": [
            "worldquant.alpha040",  # IC_IR=+0.151
            "worldquant.alpha094",  # IC_IR=+0.110
            "worldquant.alpha016",  # IC_IR=+0.110
            "worldquant.alpha073",  # IC_IR=+0.104
            "worldquant.alpha035",  # IC_IR=+0.103
        ],
        "low": [
            "worldquant.alpha040",  # IC_IR=+0.164
            "worldquant.alpha094",  # IC_IR=+0.135
            "worldquant.alpha073",  # IC_IR=+0.119
            "worldquant.alpha016",  # IC_IR=+0.118
            "worldquant.alpha044",  # IC_IR=+0.106
        ],
    },
    "dispersion": {
        "high": [
            "worldquant.alpha040",  # IC_IR=+0.124
            "worldquant.alpha094",  # IC_IR=+0.110
            "worldquant.alpha016",  # IC_IR=+0.097
            "worldquant.alpha029",  # IC_IR=+0.093
            "worldquant.alpha039",  # IC_IR=+0.091
        ],
        "normal": [
            "worldquant.alpha040",  # IC_IR=+0.147
            "worldquant.alpha094",  # IC_IR=+0.134
            "worldquant.alpha016",  # IC_IR=+0.105
            "worldquant.alpha037",  # IC_IR=+0.104
            "worldquant.alpha044",  # IC_IR=+0.100
        ],
        "low": [
            "worldquant.alpha040",  # IC_IR=+0.176
            "worldquant.alpha094",  # IC_IR=+0.127
            "worldquant.alpha044",  # IC_IR=+0.115
            "worldquant.alpha016",  # IC_IR=+0.114
            "worldquant.alpha015",  # IC_IR=+0.110
        ],
    },
    "liquidity": {
        "high": [
            "worldquant.alpha040",  # IC_IR=+0.081
            "worldquant.alpha037",  # IC_IR=+0.080
            "worldquant.alpha036",  # IC_IR=+0.076
            "worldquant.alpha033",  # IC_IR=+0.068
            "worldquant.alpha025",  # IC_IR=+0.066
        ],
        "normal": [
            "worldquant.alpha040",  # IC_IR=+0.164
            "worldquant.alpha094",  # IC_IR=+0.136
            "worldquant.alpha016",  # IC_IR=+0.121
            "worldquant.alpha044",  # IC_IR=+0.115
            "worldquant.alpha035",  # IC_IR=+0.100
        ],
        "starved": [
            "worldquant.alpha040",  # IC_IR=+0.200
            "worldquant.alpha094",  # IC_IR=+0.170
            "worldquant.alpha073",  # IC_IR=+0.162
            "worldquant.alpha029",  # IC_IR=+0.153
            "worldquant.alpha044",  # IC_IR=+0.131
        ],
    },
}
# <<< REGIME_FACTOR_SETS END


def all_factors() -> list[str]:
    """全部 state 候选因子的并集，按首次出现的顺序去重。

    L0 等权基线、L1 静态 ICIR 基线（README §4）不区分 regime，用的就是这个并集。
    """
    seen: dict[str, None] = {}
    for states in REGIME_FACTOR_SETS.values():
        for names in states.values():
            for name in names:
                seen.setdefault(name, None)
    return list(seen)
