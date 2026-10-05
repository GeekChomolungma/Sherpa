"""ML alpha 滚动训练的参数。这里是**默认值**，所有 ML 模型共用；某个模型要不一样，就在它的类上写
`training_overrides = {"label_transform": "raw_clip", ...}`（键 = 下面 `as_dict()` 的键），`for_model()` 合并出
这个模型的有效配置。改了任何一项（默认值或覆盖），该模型的配置指纹就对不上，要 `--force` 重训
（或者给新配置开一个新的模型名），不会悄悄混用两套配置训练出来的模型。

流动性范围（哪些 symbol 参与特征排名、损失计算、推断）不在这里：它是模型的一部分，写在 `FeatureSpec.liquidity`
（`sherpa/alpha/custom/ml/models.py`），进特征指纹；训练脚本开头校验它跟研究线 `track.json` 的评估掩码一致。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping, Optional

# ---- 滚动时间表（单位：bar；研究周期 4h，一天 6 根）----

# 每隔多少根 bar 重训一次：20 天。每个模型只服务到下一次重训为止。
RETRAIN_EVERY_BARS: int = 6 * 20
# 第一次训练前至少要有多少根 bar 的历史：180 天。更早的行没有模型，打分为 NaN（相当于 alpha 的 warm-up）。
MIN_TRAIN_BARS: int = 6 * 180
# 训练窗口：None = 扩展窗口（从研究起点一直用到 τ）；整数 = 滑动窗口，只用 τ 之前这么多根 bar。
# 2026-10-05 改成滑动 60 天：加密市场变化快，旧数据逐步遗忘（扩展窗口下最后几个重训时点要用 4 年的数据）。
TRAIN_WINDOW_BARS: Optional[int] = 6 * 60
# 训练分两步（trainer.train_fold）：
#   ① 早停：训练窗口里最近 INNER_VALID_BARS 根 bar 做内部验证段，前面（隔 horizon + delay 根 bar）做拟合段，
#      在验证段上按 IC_IR 早停，得到最佳轮数；
#   ② 重训：用整个训练窗口（拟合段 + 间隔 + 验证段）按最佳轮数重新训练，不再早停，保存这一步的模型。
#      这样最近 20 天也参与长树，模型学到的数据一直到 τ − (horizon + delay) 根 bar，不会隔着验证段去预测。
INNER_VALID_BARS: int = 6 * 20

# ---- 标签 ----

# 训练标签持有几根 bar。None = 跟 `research_config.json` 的 label.horizon_bars 一致（1 根）。只影响训练用的标签，
# 不影响研究流水线评估：阶段一的 IC 仍按全局口径做诊断，关卡3 的回测本来就不依赖 IC 标签的持有期。
LABEL_HORIZON_BARS: Optional[int] = None
# 训练标签的形态（dataset.build_training_frame）："rank" = 掩码内截面排名；"raw_clip" = 原始收益、每期 1%/99% 截尾。
# 2026-10-05 探索实验：原始收益标签明显更赚钱（排名标签奖励中位数效应，Top-K 等权赚的是平均收益），见 MLalpha/experiments/FINDINGS.md
LABEL_TRANSFORM: str = "rank"
# 标签先剥离 Beta / Size 暴露再训练（ML_ALPHA_DESIGN.md §5.5）。默认不做。
NEUTRALIZE_LABEL: bool = False

# ---- 损失 ----

# "ic_ir"：逐期加权 Pearson IC 的 IC_IR（objective.py）；"l2_rank"：对截面排名标签做加权 MSE 回归（对照基线）。
OBJECTIVE: str = "ic_ir"
# 首尾加权：标签排名在首尾各 TAIL_QUANTILE 内的行，权重 TAIL_WEIGHT（其余为 1）。TAIL_WEIGHT = 1 就是普通 IC。
TAIL_QUANTILE: float = 0.2
TAIL_WEIGHT: float = 3.0
# 损失掩码内少于这么多个 symbol 的时期不参与损失。
MIN_PERIOD_ROWS: int = 20

# ---- LightGBM ----

SEEDS: tuple[int, ...] = (0, 1, 2)  # 每个重训时点训练几个随机种子，推断时取平均
NUM_BOOST_ROUND: int = 500
EARLY_STOPPING_ROUNDS: int = 50
LGB_PARAMS: dict[str, Any] = {
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 500,  # 低信噪比，叶子要大
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 10.0,
    "max_bin": 63,
    "num_threads": 0,
    "verbose": -1,
}


def as_dict() -> dict[str, Any]:
    """默认训练配置（键 = `TrainConfig` 的字段，也是模型 `training_overrides` 能写的键）。"""
    return {
        "retrain_every_bars": RETRAIN_EVERY_BARS,
        "min_train_bars": MIN_TRAIN_BARS,
        "train_window_bars": TRAIN_WINDOW_BARS,
        "inner_valid_bars": INNER_VALID_BARS,
        "refit_on_full_window": True,
        "label_horizon_bars": LABEL_HORIZON_BARS,
        "label_transform": LABEL_TRANSFORM,
        "neutralize_label": NEUTRALIZE_LABEL,
        "objective": OBJECTIVE,
        "tail_quantile": TAIL_QUANTILE,
        "tail_weight": TAIL_WEIGHT,
        "min_period_rows": MIN_PERIOD_ROWS,
        "seeds": list(SEEDS),
        "num_boost_round": NUM_BOOST_ROUND,
        "early_stopping_rounds": EARLY_STOPPING_ROUNDS,
        "lgb_params": LGB_PARAMS,
    }


@dataclass(frozen=True)
class TrainConfig:
    """一个模型的有效训练配置 = 默认值（上面的常量）+ 模型类上的 `training_overrides`。写进模型清单、参与配置指纹。"""

    retrain_every_bars: int
    min_train_bars: int
    train_window_bars: Optional[int]
    inner_valid_bars: int
    refit_on_full_window: bool
    label_horizon_bars: Optional[int]
    label_transform: str
    neutralize_label: bool
    objective: str
    tail_quantile: float
    tail_weight: float
    min_period_rows: int
    seeds: list[int]
    num_boost_round: int
    early_stopping_rounds: int
    lgb_params: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def for_model(overrides: Mapping[str, Any]) -> TrainConfig:
    """默认配置 + 模型的覆盖项。覆盖项的键写错直接报错，不会悄悄被忽略。"""
    names = {f.name for f in fields(TrainConfig)}
    unknown = set(overrides) - names
    if unknown:
        raise ValueError(f"training_overrides 里有不认识的键 {sorted(unknown)}，可选 {sorted(names)}")
    merged = {**as_dict(), **overrides}
    merged["seeds"] = list(merged["seeds"])
    return TrainConfig(**merged)
