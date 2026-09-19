"""世坤101研究项目 · 第二步（分类五·复合极值与非线性时序衰减类，12 个因子）。

见 `_category_runner.run_category` 的说明——本脚本自己对本分类内每个因子重新跑一遍第一层
过滤 + 第二层向量化回测，不依赖 `run_screening.py` 的输出。这个分类里的 Alpha096 因为公式
本身极度稀疏（相关系数的输入是低离散度的时序秩，短窗口下经常方差为 0），大概率在第一层
就直接被判"没有信息量"甚至算不出 IC，不代表实现有问题，见
`tests/alpha/test_worldquant.py` 里对它的专门说明。

运行：
    CH_HOST=... CH_PASSWORD=... python research/alpha_research/worldquant_101/composite/run_vectorized.py
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sherpa.alpha.worldquant import composite

from _category_runner import run_category

ALPHA_CLASSES = [getattr(composite, name) for name in composite.__all__]

if __name__ == "__main__":
    run_category(ALPHA_CLASSES, label="复合极值与非线性时序衰减类")
