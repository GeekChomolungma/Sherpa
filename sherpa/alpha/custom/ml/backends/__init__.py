"""模型后端（推断侧）：同一套特征 / 标签 / 滚动时间表 / 模型清单，底下换不同的模型架构。**一种架构一个文件**：

| 后端名 | 文件 | 模型文件 | 训练端（`research/ml_training/trainers/`） |
| --- | --- | --- | --- |
| `lightgbm` | `lgb.py` | `seed<k>.txt` | `trainers/lgb.py` |
| `xgboost` | `xgb.py` | `seed<k>.json` | `trainers/xgb.py` |
| `lstm` | `lstm.py`（网络结构、输入预处理、checkpoint 也在这里，训练端直接复用） | `seed<k>.pt` | `trainers/lstm.py` |

共用的输入 / 接口在 `base.py`。用哪个后端写在模型类的 `training_overrides["backend"]`，训练时记进模型清单，推断按清单选
（`Manifest.backend`）；没写就是 `lightgbm`，旧清单不用改。

**加一种新架构**：① 这里新建一个文件，写 `Backend` 子类（`load` / `predict`，序列类输入用 `ModelInputs.sequences`），
在下面 `BACKENDS` 登记；② 训练端 `research/ml_training/trainers/` 新建同名文件写训练循环，在 `trainer.train_fold` 里分派；
③ `research/ml_training/config.py` 加它的超参数默认值（`BACKEND_PARAMS`）。

各后端模块在 `get_backend` 第一次用到时才 import，ML 库（lightgbm / xgboost / torch）也是：没装的后端不影响其它后端和
`import sherpa.alpha.custom`。
"""

from __future__ import annotations

from importlib import import_module
from typing import Mapping

from .base import DEFAULT_BACKEND, Backend, ModelInputs, predict_ensemble

# 后端名 -> (模块, 类名)
BACKENDS: Mapping[str, tuple[str, str]] = {
    "lightgbm": (".lgb", "LightGBMBackend"),
    "xgboost": (".xgb", "XGBoostBackend"),
    "lstm": (".lstm", "LSTMBackend"),
}


def get_backend(name: str) -> Backend:
    try:
        module, cls = BACKENDS[name]
    except KeyError:
        raise ValueError(f"未知的模型后端 {name!r}，可选 {sorted(BACKENDS)}") from None
    return getattr(import_module(module, __name__), cls)()


__all__ = ["BACKENDS", "DEFAULT_BACKEND", "Backend", "ModelInputs", "get_backend", "predict_ensemble"]
