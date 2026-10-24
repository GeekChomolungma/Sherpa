"""XGBoost 后端：每行看自己的 K 个特征（跟 LightGBM 同一种输入），模型文件是 XGBoost JSON 格式。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .base import Backend, ModelInputs


class XGBoostBackend(Backend):
    name = "xgboost"
    suffix = ".json"

    def load(self, path: Path) -> Any:
        import xgboost  # noqa: PLC0415

        booster = xgboost.Booster()
        booster.load_model(str(path))
        return booster

    def predict(self, model: Any, inputs: ModelInputs, rows: np.ndarray) -> np.ndarray:
        import xgboost  # noqa: PLC0415

        return model.predict(xgboost.DMatrix(inputs.rows(rows), missing=np.nan))
