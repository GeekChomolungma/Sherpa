"""诊断 RankIC 和 Top-K 收益为什么对不上：池内按打分分 5 组的平均未来收益（1 根 / 6 根）、多头腿 / 空头腿各自的零成本收益。

    python research/alpha_research/tradecraft/experiments/diagnose_legs.py --batch b2_refine --variants flat_full,bs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import explore  # noqa: E402

from sherpa.metrics.factor import forward_returns  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    parser.add_argument("--variants", required=True)
    args = parser.parse_args()
    panel = explore.load_panel()
    scope = explore.TRADECRAFT_LIQUIDITY.mask(panel)
    fwd = {h: forward_returns(panel.close, horizon=h, delay=explore.DELAY).where(scope) for h in (1, 6)}
    seg = {"选择段": panel.close.index < explore.VALIDATION_START, "验证段": panel.close.index >= explore.VALIDATION_START}
    rows = []
    for name in args.variants.split(","):
        base, params, _ = explore.BATCHES[args.batch][name]
        score = explore.make_alpha(base, params, name).compute(panel)
        bucket = score.rank(axis=1, pct=True).apply(lambda r: np.ceil(r * 5), axis=1)  # 1（最低分）~ 5（最高分）
        for seg_name, mask in seg.items():
            for h in (1, 6):
                y = fwd[h][mask]
                b = bucket[mask]
                # 每组每期的等权平均收益，再对期取平均（bps / 期），以及每组的收益分布右尾（95% 分位）
                means = {q: float(y.where(b == q).mean(axis=1).mean() * 1e4) for q in range(1, 6)}
                tails = {q: float(np.nanpercentile(y.where(b == q).to_numpy(), 99) * 1e4) for q in range(1, 6)}
                rows.append({"variant": name, "segment": seg_name, "h": h,
                             **{f"Q{q}": round(means[q], 1) for q in range(1, 6)},
                             "Q5-Q1": round(means[5] - means[1], 1),
                             "Q1_p99": round(tails[1], 0), "Q5_p99": round(tails[5], 0)})
        # 多头腿 / 空头腿：top10_exit20、每 6 根调仓，零成本
        ranked = explore.evaluation.cross_sectional_rank(score)
        spec = explore.evaluation.WEIGHTINGS["top10_exit20"]
        segments = {k: pd.Series(v, index=panel.close.index) for k, v in seg.items()}
        legs = explore.evaluation.backtest(ranked, panel.close, panel.interval, spec=spec, rebalance_every=6, shift=1 + explore.DELAY,
                                           segments=segments, periods_per_year=explore.PERIODS_PER_YEAR, legs=True)
        for r in legs:
            if r["cost_model"] in ("zero", "zero:long_leg", "zero:short_leg"):
                print(f"  {name:<12} {r['cost_model']:<15} {r['segment']}  毛 Sharpe {r['gross_sharpe']:+.2f}  年化 {r.get('net_ann_return', float('nan')):+.1%}")
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    main()
