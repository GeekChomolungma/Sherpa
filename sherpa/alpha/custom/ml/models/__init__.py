"""具体注册的模型 alpha，**一个模型家族一个文件**。MLalpha 研究线（`track.json` 的 `alphas.modules =
["sherpa.alpha.custom.ml.models"]`）按这个包路径挑因子，子模块里的模型都算在内，加新文件不用改研究线配置。

| 文件 | 家族 | 模型 |
| --- | --- | --- |
| `lgbm.py` | LightGBM | `LgbmV1` – `LgbmV4`（基线 V4） |
| `lstm.py` | LSTM | `LstmV5`（V4 的特征 + LSTM 看 1 天，滑动 365 天窗口）、`LstmV5Win60`（同上，滑动 60 天窗口的对照）、`LstmV5Expanding`（同上，扩展窗口的对照）、`LstmV5Win60Seq42`（60 天窗口 + 看 7 天） |

**加一个新家族**（比如 XGBoost / LSTM）：新建 `xgb.py` / `lstm.py`，照 `lgbm.py` 写 `MLAlpha` 子类，`training_overrides` 里写
`"backend": "xgboost"` / `"lstm"`（模型架构本身在 `../backends/`）；然后在下面 import 它、加进 `__all__`——import 才会触发
`@register_alpha`，研究流水线才能按名字找到它。只换架构、不换特征时直接复用 `LgbmV4.spec`。
"""

from .lgbm import WORLDQUANT_L0_UNION, LgbmV1, LgbmV2, LgbmV3, LgbmV4
from .lstm import LstmV5, LstmV5Expanding, LstmV5Win60, LstmV5Win60Seq42

__all__ = ["WORLDQUANT_L0_UNION", "LgbmV1", "LgbmV2", "LgbmV3", "LgbmV4", "LstmV5", "LstmV5Expanding", "LstmV5Win60", "LstmV5Win60Seq42"]
