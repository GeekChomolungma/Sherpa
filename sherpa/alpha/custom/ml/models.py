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
from .features import DERIVATIVES_LS, FeatureSpec

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


@register_alpha
class LgbmV2(MLAlpha):
    """LightGBM 第二版基线（2026-10-05 探索实验的结论，见 research/alpha_research/MLalpha/experiments/FINDINGS.md）。

    特征、流动性范围跟 LgbmV1 完全相同，只有训练配置不同：
    - 标签持有 1 天（6 根 bar）：4 小时换手太高，12 小时 / 2 天都更差；
    - 原始收益标签（每期 1%/99% 截尾）：排名标签奖励"排名靠前"的中位数效应，Top-K 等权赚的是平均收益；
    - 9 个随机种子集成：单个模型树少、随机性大，两组种子的打分截面相关只有 0.43–0.50；
    - 扩展窗口：探索实验里验证段最强（h6_raw_exp_ens9）。
    之后的新模型（新特征、NN……）都先跟它比。
    """

    name = "ml_lgbm_v2"
    model_name = "lgbm_v2"
    spec = FeatureSpec(
        name="lgbm_v2",
        version=1,
        alphas=WORLDQUANT_L0_UNION,
        liquidity=LiquidityFilter(min_percentile=0.5, seasoning_period=SEASONING_PERIOD, lookback=DEFAULT_LOOKBACK),
    )
    training_overrides = {
        "label_horizon_bars": 6,
        "label_transform": "raw_clip",
        "seeds": list(range(9)),
        "train_window_bars": None,
    }


@register_alpha
class LgbmV3(MLAlpha):
    """LightGBM 第三版：LgbmV2 + A 组 4 个多空比特征（`DERIVATIVES_LS`，数据来自 `market.fapi_ls_ratio_*`）。

    2026-10-09 探索实验（research/alpha_research/MLalpha/experiments/FINDINGS_DERIVATIVES.md）：同一套 V2 配置下只改
    特征集，18 个种子集成后吃单净 Sharpe 中位数 选择段 −0.41 → +0.12、验证段 0.59 → 0.73，两段都为正的组合占比
    0.26 → 0.52；剥离风格后的 alpha_sharpe 选择段 −0.27 → +0.25，低波动暴露没有增加。两组独立种子下选择段都为正，
    是本批唯一做到这一点的配置。OI 进阶特征（`DERIVATIVES_OI`）消融里拖累，没有加。
    种子数从 9 加到 18：9 种子集成换一组种子，选择段中位数仍能差 0.4。
    """

    name = "ml_lgbm_v3"
    model_name = "lgbm_v3"
    spec = FeatureSpec(
        name="lgbm_v3",
        version=1,
        alphas=WORLDQUANT_L0_UNION,
        liquidity=LiquidityFilter(min_percentile=0.5, seasoning_period=SEASONING_PERIOD, lookback=DEFAULT_LOOKBACK),
        derivatives=DERIVATIVES_LS,
    )
    training_overrides = {
        "label_horizon_bars": 6,
        "label_transform": "raw_clip",
        "seeds": list(range(18)),
        "train_window_bars": None,
    }
