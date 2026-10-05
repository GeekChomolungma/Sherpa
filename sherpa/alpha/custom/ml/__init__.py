"""自定义因子·机器学习模型主题：滚动训练的模型包装成普通 alpha。设计见上一级目录的 `ML_ALPHA_DESIGN.md`。

- `features.py`：特征构建，训练和推断共用；
- `manifest.py`：模型清单（每个模型服务哪段时间）；
- `alpha.py`：`MLAlpha` 基类，只推断；
- `models.py`：具体注册的模型 alpha。

训练在 `research/ml_training/`。
"""

from .alpha import MLAlpha
from .features import FeatureSpec, build_features
from .models import LgbmV1, LgbmV2

__all__ = ["MLAlpha", "FeatureSpec", "build_features", "LgbmV1", "LgbmV2"]
