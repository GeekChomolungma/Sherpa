"""世坤101研究项目 · 第二步（分类四·高低价差与盘口结构类，18 个因子）。

见 `_category_runner.run_category` 的说明——本脚本自己对本分类内每个因子重新跑一遍第一层
过滤 + 第二层向量化回测，不依赖 `run_screening.py` 的输出。

运行：
    CH_HOST=... CH_PASSWORD=... python research/worldquant_101/microstructure/run_vectorized.py
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sherpa.alpha.worldquant import microstructure

from _category_runner import run_category

ALPHA_CLASSES = [getattr(microstructure, name) for name in microstructure.__all__]

if __name__ == "__main__":
    run_category(ALPHA_CLASSES, label="高低价差与盘口结构类")
