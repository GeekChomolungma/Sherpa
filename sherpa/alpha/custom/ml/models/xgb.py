"""XGBoost 模型家族（`backend` = xgboost，架构见 `../backends/xgb.py`）。

跟 LightGBM 家族共用同一套特征 / 标签 / 滚动时间表 / 损失（IC_IR 的同一个梯度函数），只换树模型的实现。
"""

from __future__ import annotations

from ....base import register_alpha
from ..alpha import MLAlpha
from .lgbm import LgbmV4


@register_alpha
class XgbV5(MLAlpha):
    """XGBoost 第一版：LgbmV4 的特征（30 列）和训练配置原样不动（持有 6 根、原始收益标签、扩展窗口、18 种子），只把 LightGBM 换成 XGBoost。

    来自探索第九批 case `x_v4`（`research/alpha_research/MLalpha/experiments/FINDINGS_BACKENDS.md`）：跟 V4 打分截面相关 0.79，
    属于同一类模型，收益表上不算赢。定型成正式模型类是为了让三种架构（LightGBM / XGBoost / LSTM）都有一条正式研究线可以横比、
    可视化（2026-10-27）。训练在 CPU 上（`nthread` 8）。产出在 `runs/xgb_v5/`。
    """

    name = "ml_xgb_v5"
    model_name = "xgb_v5"
    spec = LgbmV4.spec  # 同一套特征（特征指纹相同），只换架构
    training_overrides = {
        **LgbmV4.training_overrides,
        "backend": "xgboost",
        "backend_params": {"nthread": 8},
    }
