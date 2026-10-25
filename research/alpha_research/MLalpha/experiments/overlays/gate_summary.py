"""gate_grid.csv -> 每个开关一行：39 个组合在两段的中位数，以及跟不加开关逐组合比较的胜率。按选择段 Calmar 排序。"""
import sys
from pathlib import Path

import pandas as pd

grid = pd.read_csv(Path(sys.argv[1]) / "gate_grid.csv")
keys = ["weighting", "rebalance_every", "segment"]
base = grid[grid.gate == "none"].set_index(keys)[["sharpe", "mdd"]].add_suffix("_base")
g = grid.set_index(keys).join(base).reset_index()
g["sharpe_up"] = g.sharpe > g.sharpe_base
g["mdd_up"] = g.mdd > g.mdd_base  # 回撤是负数，更大 = 更浅
rows = []
for gate, d in g.groupby("gate"):
    row = {"gate": gate}
    for seg in ("selection", "validation"):
        s = d[d.segment == seg]
        tag = seg[:3]
        row.update({f"sharpe_{tag}": s.sharpe.median(), f"mdd_{tag}": s.mdd.median(), f"calmar_{tag}": s.calmar.median(),
                    f"ret_{tag}": s.ann_ret.median(), f"inmkt_{tag}": s.in_market.median(),
                    f"win_sharpe_{tag}": s.sharpe_up.mean(), f"win_mdd_{tag}": s.mdd_up.mean()})
    wide = d.pivot_table(index=["weighting", "rebalance_every"], columns="segment", values="sharpe")
    row["both_pos"] = ((wide.selection > 0) & (wide.validation > 0)).mean()
    rows.append(row)
out = pd.DataFrame(rows).set_index("gate").sort_values("calmar_sel", ascending=False)
out.to_csv(Path(sys.argv[1]) / "gate_summary.csv")
pd.set_option("display.width", 300)
cols = [c for c in out.columns if not c.startswith("ret_")]
print(out[cols].head(int(sys.argv[2]) if len(sys.argv) > 2 else 40).round(2).to_string())
