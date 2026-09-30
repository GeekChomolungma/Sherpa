"""因子原始分数 → 研究口径分数的标准处理链：可流通性掩码 → 截面中性化残差。

阶段一体检、关卡1 去冗余、关卡2 合成、关卡3 扣费回测以前各自抄了一份 `_residual_scores`，
四份顺序和口径必须完全一致，否则"阶段一在残差口径下选出的因子，关卡3 却拿另一种口径回测"。
现在只在这里定义一次，各关只负责决定"开不开掩码 / 开不开中性化 / 掩码门槛多少"（以后由各研究线
的 track 配置给出），处理本身不再分叉。

顺序固定为先掩码、再中性化：不让插针小币的噪声分数混进当期的截面回归（`neutralize` 对缺失值
逐期排除，掩成 `NaN` 就等于这一期这个 symbol 不参与回归）。IC 标签也要用同一个掩码盖掉
（`ScorePreprocessor.mask_labels`），两边看到的截面必须是同一批 symbol。

这里的掩码是**外层**掩码——研究口径上的"可交易范围"。因子在 `compute()` 里自己用
`tradable_mask` 只在流动性好的子集里做截面运算，是因子公式的一部分，跟这一层互不替代。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence, Union

import pandas as pd

from sherpa.alpha.base import Alpha, registry
from sherpa.data.schema import BarPanel
from sherpa.metrics.tradability import tradable_mask
from sherpa.risk.neutralize import neutralize

from .style_exposure import DEFAULT_BENCHMARK_SYMBOL, default_style_exposures


@dataclass(frozen=True)
class ScorePreprocessor:
    """一份 panel 上已经算好的掩码 + 风险暴露；`None` 表示这一步关闭。

    掩码和暴露只依赖 panel，跟具体因子无关，所以对同一份 panel 只算一次，再套到每个因子上。
    frozen + 只装 DataFrame，可以直接 pickle 给多进程 worker。
    """

    mask: Optional[pd.DataFrame] = None
    exposures: Optional[Mapping[str, pd.DataFrame]] = None

    @classmethod
    def from_panel(
        cls,
        panel: BarPanel,
        *,
        benchmark_symbol: str = DEFAULT_BENCHMARK_SYMBOL,
        tradable: Union[bool, Mapping[str, Any]] = True,
        neutralize: bool = True,
    ) -> "ScorePreprocessor":
        """`tradable`：True = `tradable_mask` 默认门槛，False = 不掩码，Mapping = 覆盖部分门槛参数
        （原样透传给 `tradable_mask`，比如 `{"min_percentile": 0.6}`）。`neutralize`：是否剥离
        Beta（对 `benchmark_symbol`）/ Size 暴露（`default_style_exposures`）。"""
        mask = None
        if tradable is not False:
            params = {} if tradable is True else dict(tradable)
            mask = tradable_mask(panel.quote_volume, panel.trades_count, **params)
        exposures = default_style_exposures(panel, benchmark_symbol=benchmark_symbol) if neutralize else None
        return cls(mask=mask, exposures=exposures)

    @property
    def neutralized(self) -> bool:
        return self.exposures is not None

    def apply(self, raw_score: pd.DataFrame) -> pd.DataFrame:
        """原始分数 → 掩码 → 中性化残差。"""
        score = raw_score if self.mask is None else raw_score.where(self.mask)
        if self.exposures is not None:
            score = neutralize(score, self.exposures)
        return score

    def mask_labels(self, labels: pd.DataFrame) -> pd.DataFrame:
        """IC 标签（未来收益）套同一个掩码，保证分数和标签看的是同一批 symbol。"""
        return labels if self.mask is None else labels.where(self.mask)


def residual_score(alpha: Alpha, panel: BarPanel, preprocessor: ScorePreprocessor) -> pd.DataFrame:
    """单个因子：`alpha.compute(panel)` 后走一遍 `preprocessor`。占位因子的 `NotImplementedError` 原样抛出。"""
    return preprocessor.apply(alpha.compute(panel))


def residual_scores(
    names: Sequence[str],
    panel: BarPanel,
    preprocessor: ScorePreprocessor,
    *,
    skip_not_implemented: bool = False,
    progress: Optional[Callable[[int, int, str, float], None]] = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, str]]:
    """按 registry 的 qualified_name 批量算处理后的分数，返回 `(scores, errors)`。

    名字在 registry 里找不到直接 `KeyError`——候选名单是配置出来的，拼错属于配置错误，要第一时间
    暴露。`skip_not_implemented=True` 时占位因子（缺行业/市值数据的世坤因子）记进 `errors` 跳过，
    否则原样抛出（合成/回测阶段名单里出现占位因子说明上游配置有问题，不该静默少一个因子）。
    `progress(i, total, name, elapsed_seconds)` 每算完一个因子回调一次，打印交给调用方。
    """
    scores: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    started = time.monotonic()
    for i, name in enumerate(names, 1):
        alpha = registry.get(name)()
        try:
            scores[name] = residual_score(alpha, panel, preprocessor)
        except NotImplementedError as exc:
            if not skip_not_implemented:
                raise
            errors[name] = str(exc)
        if progress is not None:
            progress(i, len(names), name, time.monotonic() - started)
    return scores, errors
