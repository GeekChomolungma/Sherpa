"""LSTM 模型家族（`backend` = lstm，架构见 `../backends/lstm.py`）。

跟 LightGBM 家族共用同一套特征 / 标签 / 滚动时间表，只换模型架构：每行看同一个币最近 `seq_len` 根 bar 的特征序列。
"""

from __future__ import annotations

from ....base import register_alpha
from ..alpha import MLAlpha
from .lgbm import LgbmV4


@register_alpha
class LstmV5(MLAlpha):
    """LSTM 第一版：LgbmV4 的特征（30 列）和训练配置（持有 6 根、原始收益标签、扩展窗口），换成 LSTM 看最近 6 根（1 天）。

    2026-10-24 探索第九批（research/alpha_research/MLalpha/experiments/FINDINGS_BACKENDS.md，case `l6` = `l6_a` + `l6_b`）：
    12 种子 吃单中位数 选择段 / 验证段 1.96 / 0.77（同批 V4 0.88 / 0.49），两段都为正 87%（V4 69%），两组不重叠的种子都成立；
    看 30 根（5 天）的版本两段都更差。种子 0–11 = 探索里两组 6 种子的并集；`num_threads` 跟探索时相同（8），保证结果逐位可比。
    """

    name = "ml_lstm_v5"
    model_name = "lstm_v5"
    spec = LgbmV4.spec  # 同一套特征（特征指纹相同），只换架构
    training_overrides = {
        **LgbmV4.training_overrides,
        "seeds": list(range(12)),
        "backend": "lstm",
        "backend_params": {"seq_len": 6, "num_threads": 8},
    }
