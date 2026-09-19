"""世坤101研究项目 · 第二步（分类二·量价关系与流动性交叉类，28 个因子）。

先跑同目录上级的 `run_screening.py` 看一眼整体排行榜也可以，但这个脚本不依赖那一步的
输出——自己对本分类内每个因子重新跑一遍第一层过滤 + 第二层向量化回测，见
`_category_runner.run_category`。Alpha056 依赖市值(cap)，`BarPanel` 不支持，会打印"跳过"。

运行：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/worldquant_101/price_volume/run_vectorized.py
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sherpa.alpha.worldquant import price_volume

from _category_runner import run_category

ALPHA_CLASSES = [getattr(price_volume, name) for name in price_volume.__all__]

if __name__ == "__main__":
    run_category(ALPHA_CLASSES, label="量价关系与流动性交叉类")
