"""世坤101研究项目 · 第二步（分类一·行业与板块中性化类，18 个因子）。

这个分类的全部 18 个因子都依赖 `indneutralize`/`IndClass`，`BarPanel` 没有行业分类字段——
运行这个脚本预期看到 18 行"跳过"，这是正确的结果，不是 bug，见
`sherpa/alpha/worldquant/industry/base.py`。留着这个脚本（而不是干脆不建这个文件夹）是为了
跟另外四个分类保持同样的目录结构，以后真有行业分类数据源接入时，这里就是现成的落点。

运行：
    CH_HOST=... CH_PASSWORD=... python research/worldquant_101/industry/run_vectorized.py
"""

from __future__ import annotations

import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sherpa.alpha.worldquant import industry

from _category_runner import run_category

ALPHA_CLASSES = [getattr(industry, name) for name in industry.__all__ if name != "IndustryNeutralPlaceholder"]

if __name__ == "__main__":
    run_category(ALPHA_CLASSES, label="行业与板块中性化类")
