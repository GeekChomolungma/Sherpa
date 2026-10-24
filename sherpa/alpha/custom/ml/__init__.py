"""自定义因子·机器学习模型主题：滚动训练的模型包装成普通 alpha。设计见上一级目录的 `ML_ALPHA_DESIGN.md`。

所有模型共用的基础设施：

- `features.py`：特征构建，训练和推断共用；
- `manifest.py`：模型清单（每个模型服务哪段时间、用哪个后端训练的）；
- `alpha.py`：`MLAlpha` 基类，只推断。

按模型隔开的两个子包：

- `backends/`：模型架构（LightGBM / XGBoost / LSTM），一种架构一个文件，负责读模型文件、打分；
- `models/`：具体注册的模型 alpha，一个模型家族一个文件（`models/lgbm.py` = LgbmV1–V4）。

训练在 `research/ml_training/`。
"""

from .alpha import MLAlpha
from .features import FeatureSpec, build_features
from .models import LgbmV1, LgbmV2, LgbmV3, LgbmV4

__all__ = ["MLAlpha", "FeatureSpec", "build_features", "LgbmV1", "LgbmV2", "LgbmV3", "LgbmV4"]
