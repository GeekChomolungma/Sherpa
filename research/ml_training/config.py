"""ML alpha 滚动训练的参数。这里是**默认值**，所有 ML 模型共用；某个模型要不一样，就在它的类上写
`training_overrides = {"label_transform": "raw_clip", ...}`（键 = 下面 `as_dict()` 的键），`for_model()` 合并出
这个模型的有效配置。改了任何一项（默认值或覆盖），该模型的配置指纹就对不上，要 `--force` 重训
（或者给新配置开一个新的模型名），不会悄悄混用两套配置训练出来的模型。

模型架构（`backend`）也在这里选：`lightgbm`（默认）/ `xgboost` / `lstm`，各自的超参数默认值是下面的 `LGB_PARAMS` /
`XGB_PARAMS` / `LSTM_PARAMS`，模型类用 `training_overrides = {"backend": "xgboost", "backend_params": {...}}` 覆盖个别项。
特征、标签、损失（IC_IR）、滚动时间表、两步训练（早停 → 整窗重训）对所有架构都相同，换架构只换"模型本身"。

流动性范围（哪些 symbol 参与特征排名、损失计算、推断）不在这里：它是模型的一部分，写在 `FeatureSpec.liquidity`
（`sherpa/alpha/custom/ml/models/`），进特征指纹；训练脚本开头校验它跟研究线 `track.json` 的评估掩码一致。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
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
    # 训练集分箱的随机数固定住。不固定时，LightGBM 在第一次训练时用"当时那个 seed"派生的随机数给训练集抽样分箱
    # （行数 > bin_construct_sample_cnt = 20 万时才抽样），之后的种子都沿用这份分箱——同一个种子的结果会取决于它前面
    # 先训了哪个种子（同一份训练集，种子 10 的早停轮数在"先训种子 0 / 9 / 10"时是 16 / 22 / 107；固定后都是 23）。
    # 固定后，同一配置、同一组种子不管分几组跑都得到同一批模型，探索（run_experiments.py）跟正式训练才能逐格一致。
    "data_random_seed": 0,
}

# ---- 模型架构 ----

# 默认后端。LightGBM 模型的训练配置里不写 backend / backend_params 两项（`TrainConfig.to_dict`），V1–V4 的配置指纹因此不变。
BACKEND: str = "lightgbm"

# XGBoost：尽量对齐 LGB_PARAMS 的含义，两者差别只来自算法本身。按叶子数生长（lossguide + max_leaves 31 = num_leaves），
# min_child_weight 500 ≈ min_data_in_leaf 500（IC_IR 损失的二阶导取常数 1，每行 hessian 都是 1），subsample / colsample /
# lambda / max_bin 一一对应。base_score 0：自定义损失下初始打分是常数，IC 对平移不敏感，取 0 只是让模型文件好读。
# 树的轮数、早停沿用 NUM_BOOST_ROUND / EARLY_STOPPING_ROUNDS。
XGB_PARAMS: dict[str, Any] = {
    "eta": 0.05,
    "tree_method": "hist",
    "grow_policy": "lossguide",
    "max_leaves": 31,
    "max_depth": 0,
    "min_child_weight": 500.0,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "lambda": 10.0,
    "max_bin": 63,
    "base_score": 0.0,
    "nthread": 0,  # 0 = 全部核，同 LGB_PARAMS 的 num_threads
    "disable_default_eval_metric": 1,
    "verbosity": 0,
}

# LSTM：每行看同一个币最近 seq_len 根 bar 的特征序列（含当前这根），**seq_len 没有默认值，模型类必须写明**——它同时决定
# 推断要往回多看几根 bar（MLAlpha.min_lookback）。损失 = 每个 batch 内各期加权 IC 的 −IC_IR（跟树模型同一个定义，
# 首尾加权同样生效）；按 epoch 早停（内部验证段 IC_IR 连续 patience 个 epoch 没刷新就停），再用整个窗口按最佳 epoch 数重训。
LSTM_PARAMS: dict[str, Any] = {
    "hidden_size": 32,
    "num_layers": 1,
    "dropout": 0.0,
    "learning_rate": 1e-3,
    "weight_decay": 1e-4,
    "periods_per_batch": 32,  # 一个 batch 放几期（几根 bar）的全部截面行；IC_IR 在 batch 内的这几期上算
    "max_epochs": 30,
    "patience": 5,
    "num_threads": 0,  # torch 线程数，0 = torch 默认
}
LSTM_REQUIRED: tuple[str, ...] = ("seq_len",)

BACKEND_PARAMS: dict[str, dict[str, Any]] = {"lightgbm": {}, "xgboost": XGB_PARAMS, "lstm": LSTM_PARAMS}
BACKEND_REQUIRED: dict[str, tuple[str, ...]] = {"lstm": LSTM_REQUIRED}


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
        "backend": BACKEND,
        "backend_params": {},
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
    backend: str = BACKEND
    backend_params: dict[str, Any] = field(default_factory=dict)  # 非 LightGBM 后端的有效超参数（默认值 + 覆盖）

    def to_dict(self) -> dict[str, Any]:
        """写进模型清单、参与配置指纹的内容。LightGBM 不写 backend / backend_params（跟引入多后端之前逐字节相同，
        已有模型不用重训）；其它后端不写 lgb_params（用不到，写进去只会让人误以为它生效）。"""
        out = asdict(self)
        if self.backend == "lightgbm":
            del out["backend"], out["backend_params"]
        else:
            del out["lgb_params"]
        return out


def for_model(overrides: Mapping[str, Any]) -> TrainConfig:
    """默认配置 + 模型的覆盖项。覆盖项的键写错直接报错，不会悄悄被忽略。"""
    names = {f.name for f in fields(TrainConfig)}
    unknown = set(overrides) - names
    if unknown:
        raise ValueError(f"training_overrides 里有不认识的键 {sorted(unknown)}，可选 {sorted(names)}")
    merged = {**as_dict(), **overrides}
    merged["seeds"] = list(merged["seeds"])
    backend = merged["backend"]
    if backend not in BACKEND_PARAMS:
        raise ValueError(f"未知的 backend {backend!r}，可选 {sorted(BACKEND_PARAMS)}")
    given = dict(merged["backend_params"])
    if backend == "lightgbm" and given:
        raise ValueError("LightGBM 的超参数写在 lgb_params，不用 backend_params")
    defaults = BACKEND_PARAMS[backend]
    required = BACKEND_REQUIRED.get(backend, ())
    unknown = set(given) - set(defaults) - set(required)
    if unknown:
        raise ValueError(f"{backend} 的 backend_params 里有不认识的键 {sorted(unknown)}，可选 {sorted(set(defaults) | set(required))}")
    missing = [k for k in required if k not in given]
    if missing:
        raise ValueError(f"{backend} 必须在 backend_params 里写明 {missing}")
    merged["backend_params"] = {**defaults, **given}
    return TrainConfig(**merged)
