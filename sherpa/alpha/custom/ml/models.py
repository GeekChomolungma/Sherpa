"""具体注册的模型 alpha。MLalpha 研究线（`research/alpha_research/MLalpha/`）按这个模块挑因子。

每个模型配置一个子类：特征清单（`FeatureSpec`）、模型名（= 模型文件目录名）都写在类属性上。特征清单变了就换
`version` 或开新的模型名，旧模型文件不能拿新特征推断（`MLAlpha.manifest()` 会校验）。
"""

from __future__ import annotations

import sherpa.alpha.worldquant  # noqa: F401  B 组特征要用世坤因子，先触发注册

from sherpa.metrics.tradability import DEFAULT_LOOKBACK, SEASONING_PERIOD

from ...base import register_alpha
from ...liquidity import LiquidityFilter
from .alpha import MLAlpha
from .features import FeatureSpec

# B 组第一批：worldquant_101 研究线关卡1 去冗余后的候选并集（关卡2 L0 方案用的那 13 个，2026-10-01 取）。
# 写死在这里而不是运行时读那份交接文件：世坤研究线重跑后名单会变，特征必须有固定版本。
# 注意：这份名单是在世坤研究线的**选择段**上选出来的，所以 ML alpha 在选择段上的样本外表现会偏乐观，
# 验证段才是干净的比较（ML_ALPHA_DESIGN.md §6）。
WORLDQUANT_L0_UNION: tuple[str, ...] = (
    "worldquant.alpha040",
    "worldquant.alpha044",
    "worldquant.alpha094",
    "worldquant.alpha016",
    "worldquant.alpha015",
    "worldquant.alpha050",
    "worldquant.alpha029",
    "worldquant.alpha073",
    "worldquant.alpha055",
    "worldquant.alpha025",
    "worldquant.alpha037",
    "worldquant.alpha003",
    "worldquant.alpha036",
)


@register_alpha
class LgbmV1(MLAlpha):
    """LightGBM 第一版：A（原始字段衍生）+ B（世坤 L0 并集 13 个）+ C（市场状态连续变量）。"""

    name = "ml_lgbm_v1"
    model_name = "lgbm_v1"
    spec = FeatureSpec(
        name="lgbm_v1",
        version=1,
        alphas=WORLDQUANT_L0_UNION,
        # 流动性范围：滚动 120 根成交额中位数排在截面前一半，不设绝对地板，上线满 20 根。
        # 必须跟 MLalpha 研究线 track.json 的 tradable_mask 一致（训练脚本开头校验），
        # 那边是 {"min_percentile": 0.5, "min_quote_volume": 0, "min_trades_count": 0}，其余取 tradable_mask 默认值。
        liquidity=LiquidityFilter(min_percentile=0.5, seasoning_period=SEASONING_PERIOD, lookback=DEFAULT_LOOKBACK),
    )
