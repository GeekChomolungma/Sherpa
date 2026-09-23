"""交易截面可流通性掩码：区分"上线了"和"现在真的有流动性"。

加密市场里大量长尾小币会持续打印K线，但实际订单簿早已枯竭——一根插针就能左右整个截面的
秩相关，而且拿这种因子跑出来的选币结果在真实执行时根本没有深度接得住。`Universe.as_of()`
只解决"这个 symbol 在 t 时刻有没有上线"（生存偏差意义上的准入），完全不管"上线之后是不是
还有真实成交"——这两件事是独立的问题，这个模块只处理后者。

跟 `sherpa.metrics.regime` 一样只吃 pandas 对象、只用 `.rolling()`，不认识 `BarPanel`
（`sherpa.metrics` 包级约定，见 `sherpa/metrics/__init__.py`）。也故意不看 `close`/收益率——
掩码只能用成交量/成交笔数这类"有没有真实交易活动"的信号来判定，不能用价格或收益率本身，
否则等于用因变量去筛自变量，会引入新的、更隐蔽的选择性偏差。
"""

from __future__ import annotations

import pandas as pd

DEFAULT_LOOKBACK = 120
SEASONING_PERIOD = 20

def tradable_mask(
    quote_volume: pd.DataFrame,
    trades_count: pd.DataFrame,
    *,
    lookback: int = DEFAULT_LOOKBACK,
    min_percentile: float = 0.40,
    min_quote_volume: float = 5_000_000.0,  # 120根k线内的中位值要超过 500 万usdt成交才行
    min_trades_count: float = 50_000.0,     # 120根k线内的中位值要超过 5 万 笔成交才行（默认关闭）
    seasoning_period: int = SEASONING_PERIOD,
) -> pd.DataFrame:
    """逐期判定每个 symbol 是不是"真的可流通"，输出跟 `quote_volume` 同形状的布尔矩阵。

    三条门槛都要同时满足，该 symbol 该期才算 tradable：

    1. **截面相对排名**：滚动成交额（取中位数而不是均值——对单日刷单式放量更不敏感）在
       当期截面里的百分位排名 `>= min_percentile`。用相对排名而不是固定绝对数字，是因为
       加密市场整体成交规模这几年发生数量级式变化（`research/REGIME_FRAMEWORK_GUIDE.md`
       §2），绝对门槛没法一劳永逸写死。
    2. **绝对地板**（`min_quote_volume`/`min_trades_count`，默认 0 即关闭）：纯相对排名
       在整个截面集体萎靡时会失效——"最活跃的 80%"如果全市场当时都很冷清，依然是一堆
       死币。默认关闭是因为"多少算真的活跃"这个绝对数字现在没有数据支撑，不凭空拍一个；
       等观察过真实数据分布后，调用方按需传入。
    3. **冷启动缓冲**（`seasoning_period`）：symbol 从有数据开始的前 N 根 bar 一律不算
       tradable，不管成交量多大——新币刚上线的异常放量往往是炒作性质，不代表可持续流动性。

    全部用 `.rolling()`，t 时刻的判定只用得到 `<= t` 的历史，不存在前视泄露。滚动窗口还没
    攒够数据、或者原始数据本来就是 `NaN`（还没上市）的位置，比较运算天然给出 `False`——
    保守默认：没能正面确认流通性之前不给参与资格。
    """
    rolling_quote_volume = quote_volume.rolling(lookback).median()
    rolling_trades_count = trades_count.rolling(lookback).median()

    passes_floor = (rolling_quote_volume > min_quote_volume) & (rolling_trades_count > min_trades_count)

    cross_sectional_percentile = rolling_quote_volume.rank(axis=1, pct=True)
    passes_percentile = cross_sectional_percentile >= min_percentile

    seasoned = quote_volume.notna().cumsum() > seasoning_period

    return passes_floor & passes_percentile & seasoned
