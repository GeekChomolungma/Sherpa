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
            "worldquant.alpha040",  # IC_IR=+0.584
            "worldquant.alpha016",  # IC_IR=+0.447
            "worldquant.alpha094",  # IC_IR=+0.436
            "worldquant.alpha073",  # IC_IR=+0.419
            "worldquant.alpha026",  # IC_IR=+0.405
        ],
        "bear": [
            "worldquant.alpha033",  # IC_IR=+0.254  代表冗余簇，吸收了 alpha038, alpha009, alpha101
            "worldquant.alpha083",  # IC_IR=+0.209
        ],
        "neutral": [
            "worldquant.alpha033",  # IC_IR=+0.238  代表冗余簇，吸收了 alpha038, alpha009
            "worldquant.alpha083",  # IC_IR=+0.204
            "worldquant.alpha037",  # IC_IR=+0.202
        ],
    },
    "volatility": {
        "high": [
            "worldquant.alpha033",  # IC_IR=+0.267  代表冗余簇，吸收了 alpha038, alpha009
            "worldquant.alpha083",  # IC_IR=+0.224
            "worldquant.alpha037",  # IC_IR=+0.212
        ],
        "normal": [
            "worldquant.alpha033",  # IC_IR=+0.242  代表冗余簇，吸收了 alpha038, alpha101
            "worldquant.alpha034",  # IC_IR=+0.200
            "worldquant.alpha083",  # IC_IR=+0.197
        ],
        "low": [
            "worldquant.alpha033",  # IC_IR=+0.229  代表冗余簇，吸收了 alpha009, alpha038
            "worldquant.alpha083",  # IC_IR=+0.203
            "worldquant.alpha057",  # IC_IR=+0.192
        ],
    },
    "dispersion": {
        "high": [
            "worldquant.alpha033",  # IC_IR=+0.229  代表冗余簇，吸收了 alpha038
            "worldquant.alpha034",  # IC_IR=+0.192
            "worldquant.alpha057",  # IC_IR=+0.189
            "worldquant.alpha083",  # IC_IR=+0.184
        ],
        "normal": [
            "worldquant.alpha033",  # IC_IR=+0.249  代表冗余簇，吸收了 alpha038, alpha009, alpha101
            "worldquant.alpha083",  # IC_IR=+0.203
        ],
        "low": [
            "worldquant.alpha033",  # IC_IR=+0.256  代表冗余簇，吸收了 alpha038, alpha101, alpha009
            "worldquant.alpha083",  # IC_IR=+0.238
        ],
    },
    "liquidity": {
        "high": [
            "worldquant.alpha033",  # IC_IR=+0.196  代表冗余簇，吸收了 alpha009, alpha038
            "worldquant.alpha083",  # IC_IR=+0.184
            "worldquant.alpha057",  # IC_IR=+0.173
        ],
        "normal": [
            "worldquant.alpha033",  # IC_IR=+0.263  代表冗余簇，吸收了 alpha038, alpha009, alpha101
            "worldquant.alpha083",  # IC_IR=+0.217
        ],
        "starved": [
            "worldquant.alpha033",  # IC_IR=+0.267  代表冗余簇，吸收了 alpha038, alpha101
            "worldquant.alpha094",  # IC_IR=+0.260
            "worldquant.alpha029",  # IC_IR=+0.230
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
