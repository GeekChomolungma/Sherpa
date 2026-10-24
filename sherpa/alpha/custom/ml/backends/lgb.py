"""LightGBM 后端（V1–V4）：每行看自己的 K 个特征，模型文件是 LightGBM 纯文本格式。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from .base import Backend, ModelInputs


class LightGBMBackend(Backend):
    name = "lightgbm"
    suffix = ".txt"

    def load(self, path: Path) -> Any:
        import lightgbm  # noqa: PLC0415  只在真的要推断时才需要 ML 依赖

        return lightgbm.Booster(model_file=str(path))

    def predict(self, model: Any, inputs: ModelInputs, rows: np.ndarray) -> np.ndarray:
        return model.predict(inputs.rows(rows))
