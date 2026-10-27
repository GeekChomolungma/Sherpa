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
    看 30 根（5 天）的版本两段都更差。种子 0–11 = 探索里两组 6 种子的并集。2026-10-26 起默认 GPU 训练（`device` 不写 = cuda，
    逐位可复现）；`num_threads` 只管 CPU 上的数据准备。

    **训练窗口：滑动 365 天**（2026-10-26 起；V4 和最初的 LstmV5 都是扩展窗口）。依据是训练样本的统计显著性
    （research/ml_training/README.md §8.2）：单期 6 根 RankIC 均值约 0.067、标准差约 0.134，每约 4.3 根 bar 才算一个独立样本；
    365 天窗口的拟合段约 480 个有效样本，能分辨约 0.018 的 IC 差，60 天只有约 0.055（几乎等于整个信号）。窗口固定还能让早期
    市场结构逐步被遗忘。扩展窗口版本的结果归档在 `runs/lstm_v5__expanding/`、`models/lstm_v5__expanding/`。
    """

    name = "ml_lstm_v5"
    model_name = "lstm_v5"
    spec = LgbmV4.spec  # 同一套特征（特征指纹相同），只换架构
    training_overrides = {
        **LgbmV4.training_overrides,
        "train_window_bars": 6 * 365,
        "seeds": list(range(12)),
        "backend": "lstm",
        "backend_params": {"seq_len": 6, "num_threads": 8},
    }


@register_alpha
class LstmV5Win60(LstmV5):
    """`LstmV5` 的对照：只把训练窗口换成**滑动 60 天**（2026-10-26）。

    用来检验"加密市场变化快，短窗口学到更多近期规律"是否成立，跟 365 天（`LstmV5`）、扩展窗口（`runs/lstm_v5__expanding/`）横比。
    统计上 60 天拟合段约 54 个有效样本，只能分辨约 0.055 的 IC 差（research/ml_training/README.md §8.2）——这是预期的代价，
    要看它在样本外 RankIC 上能不能用"更贴近近期"换回来。模型名带 `__win60` 后缀，产出在 `runs/lstm_v5__win60/`。
    """

    name = "ml_lstm_v5_win60"
    model_name = "lstm_v5__win60"
    training_overrides = {**LstmV5.training_overrides, "train_window_bars": 6 * 60}


@register_alpha
class LstmV5Expanding(LstmV5):
    """`LstmV5` 的对照：训练窗口用**扩展窗口**（从研究起点一直用到每个重训时点，V4 的做法；2026-10-26）。

    LstmV5 最初就是扩展窗口（CPU 训练），发现排序能力逐季衰减后改成滑动 365 天；这个类把扩展窗口版本作为显式的对照保留下来，
    跟 365 天（`LstmV5`）、60 天（`LstmV5Win60`）在同一设备（GPU）上横比。产出在 `runs/lstm_v5__expanding/`。
    """

    name = "ml_lstm_v5_expanding"
    model_name = "lstm_v5__expanding"
    training_overrides = {**LstmV5.training_overrides, "train_window_bars": None}


@register_alpha
class LstmV5Win60Seq42(LstmV5Win60):
    """`LstmV5Win60` 的对照：滑动 60 天窗口不变，每行的序列从 6 根（1 天）拉长到 **42 根（7 天）**，种子 12 → 8（0–7）（2026-10-27）。

    用来检验"让 LSTM 看更长的历史能不能学到更多"。探索第九批里扩展窗口下看 30 根不如看 6 根（`experiments/FINDINGS_BACKENDS.md`，
    case `l30`），这次换成 60 天窗口再试。跟 `LstmV5Win60`（6 根、12 种子）横比时注意种子数不同。产出在 `runs/lstm_v5__win60_seq42/`。
    """

    name = "ml_lstm_v5_win60_seq42"
    model_name = "lstm_v5__win60_seq42"
    training_overrides = {
        **LstmV5Win60.training_overrides,
        "seeds": list(range(8)),
        "backend_params": {**LstmV5Win60.training_overrides["backend_params"], "seq_len": 42},
    }
