"""`MLAlpha`：把滚动训练好的模型包装成一个普通 alpha，`compute(panel)` 返回 `(T, N)` 打分。

**只推断、不训练**。模型由离线训练（`research/ml_training/run_training.py`）按固定节奏滚动训练、冻结成文件，写进
模型清单（`manifest.py`）。`compute()` 对每一行找"服务这一行的那个模型"，用同一份特征构建（`features.py`）推断，
所以阶段一（只取选择段数据）和关卡3（取整个研究段）对同一根 bar 算出的打分完全一致。

打分的方向就是模型学出来的方向（训练目标是让打分和未来收益的截面相关尽量高），研究流水线照常按 IC 符号使用。

模型文件默认在 `research/alpha_research/MLalpha/models/<model_name>/`，环境变量 `SHERPA_ML_MODEL_ROOT` 可以换根目录
（以后实盘把模型放到别处时用）。lightgbm 在第一次加载模型时才 import：没装 ML 依赖（`pip install -e .[ml]`）时，
`import sherpa.alpha.custom` 不受影响，只有真的算 ML alpha 才会报错。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, ClassVar, Mapping

import numpy as np
import pandas as pd

from sherpa.data.schema import BarPanel

from ...base import CustomAlpha
from .features import FeatureSpec, build_features
from .manifest import Manifest, load_manifest

DEFAULT_MODEL_ROOT = Path(__file__).resolve().parents[4] / "research" / "alpha_research" / "MLalpha" / "models"


def model_root() -> Path:
    return Path(os.environ.get("SHERPA_ML_MODEL_ROOT", DEFAULT_MODEL_ROOT))


def load_booster(path: Path) -> Any:
    import lightgbm  # noqa: PLC0415  只在真的要推断时才需要 ML 依赖

    return lightgbm.Booster(model_file=str(path))


class MLAlpha(CustomAlpha):
    """模型 alpha 的基类，本身不注册。具体模型写成子类（`models.py`），用类属性给出特征清单和模型名。

    研究流水线按 qualified_name 无参实例化 alpha，所以配置只能写在类属性上，不能靠构造参数。
    """

    spec: ClassVar[FeatureSpec]
    model_name: ClassVar[str]
    # 训练配置的覆盖项（只给离线训练 `research/ml_training/` 用，推断不看）：键 = `research/ml_training/config.py`
    # 里 `as_dict()` 的键，没写的项用那边的默认值。同一条研究线里的几个模型可以用不同的标签 / 种子 / 窗口。
    training_overrides: ClassVar[Mapping[str, Any]] = {}

    def __init__(self):
        super().__init__()
        self.min_lookback = self.spec.min_lookback
        self._manifest: Manifest | None = None
        self._boosters: dict[str, Any] = {}

    @property
    def model_dir(self) -> Path:
        return model_root() / self.model_name

    def manifest(self) -> Manifest:
        if self._manifest is None:
            manifest = load_manifest(self.model_dir)
            if manifest is None:
                raise FileNotFoundError(
                    f"{self.qualified_name} 还没有训练好的模型：{self.model_dir} 下没有 manifest.json。"
                    "先跑 research/ml_training/run_training.py（MLalpha 研究线的步骤 0）"
                )
            if manifest.feature_fingerprint != self.spec.fingerprint:
                raise ValueError(
                    f"{self.qualified_name} 的特征清单变了（清单 {manifest.feature_fingerprint}，代码 {self.spec.fingerprint}），"
                    "旧模型不能用：重新训练，或者给新特征开一个新的模型名"
                )
            self._manifest = manifest
        return self._manifest

    def _predict_entry(self, entry, features: np.ndarray) -> np.ndarray:
        preds = []
        for rel in entry.files:
            booster = self._boosters.get(rel)
            if booster is None:
                booster = self._boosters[rel] = load_booster(self.model_dir / rel)
            preds.append(booster.predict(features))
        return np.mean(preds, axis=0)

    def compute(self, panel: BarPanel) -> pd.DataFrame:
        manifest = self.manifest()
        entries = manifest.sorted_entries()
        # 流动性范围跟训练时同一份（spec.liquidity）：范围外的格子 A、B 组特征全是 NaN，模型也没见过这样的行，不打分
        scope = self.spec.liquidity.mask(panel)
        features = build_features(panel, self.spec, scope)
        times = pd.DatetimeIndex(features.index.get_level_values("start_time"))
        symbols = features.index.get_level_values("symbol")
        in_scope = scope.to_numpy()[panel.close.index.get_indexer(times), panel.close.columns.get_indexer(symbols)]
        assigned = np.where(in_scope, manifest.assign(times), -1)

        values = np.full(len(features), np.nan)
        matrix = features.to_numpy(dtype="float32")
        for i in np.unique(assigned[assigned >= 0]):
            rows = assigned == i
            values[rows] = self._predict_entry(entries[i], matrix[rows])

        scores = pd.Series(values, index=features.index).unstack("symbol")
        return scores.reindex(index=panel.close.index, columns=panel.close.columns)
