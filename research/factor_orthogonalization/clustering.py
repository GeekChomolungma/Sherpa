"""相关性聚类：把候选因子按两两相关强度分成若干簇（四大关卡·关卡1 核心逻辑）。

纯函数、不碰 pandas/IO，方便单独测试。用并查集（Union-Find）实现"单链聚类
（single-linkage clustering）在固定阈值处截断"——两个因子只要 `|corr_mean| >= threshold`
就直接合并所在的簇，簇具有传递性（A 跟 B 强相关、B 跟 C 强相关，即使 A 跟 C 本身相关性不
够，三者也会被分进同一簇）。

没有用 `scipy.cluster.hierarchy`：仓库当前依赖里没有 scipy（`pyproject.toml` 只声明了
pandas/numpy/redis/clickhouse-connect），而候选因子池按设计就是研究者手动圈定的一小撮
（几个到几十个），单链聚类用几十行标准库代码就能严谨实现，不值得为这一个环节新增一个重
依赖。如果以后候选池规模显著变大、需要更精细的聚类形态（比如 complete-linkage 控制簇内
最大距离），再引入 scipy 也不迟。
"""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


class _UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_a] = root_b


def cluster_by_correlation(
    alphas: Sequence[str],
    pairwise_corr: Mapping[tuple[str, str], float],
    threshold: float,
) -> dict[str, int]:
    """返回 `{qualified_name: cluster_id}`。

    `pairwise_corr` 的 key 是 `(alpha_a, alpha_b)` 无序对（调用方保证每对只出现一次），
    value 是该对因子的截面相关均值（可正可负，函数内部自己取绝对值判断）。孤立因子（跟谁
    都没有达到阈值）自己单独成簇，簇大小为 1。

    簇编号按 `alphas` 里第一次出现该簇代表元素的顺序从 0 开始分配，只是为了让每次重跑的
    结果里簇编号保持确定性、方便跟上一版结果做 diff，不代表簇之间有大小或强度上的顺序。
    """
    uf = _UnionFind(alphas)
    for (a, b), corr in pairwise_corr.items():
        # `corr` 是 NaN 时（比如两个因子没有共同有效样本）`abs(corr) >= threshold` 天然
        # 求值为 False，不需要额外判空——直接当作"不合并"处理，跟"没有证据说明它们冗余"
        # 这个语义正好一致。
        if corr is not None and abs(corr) >= threshold:
            uf.union(a, b)

    root_to_id: dict[str, int] = {}
    assignment: dict[str, int] = {}
    for name in alphas:
        root = uf.find(name)
        if root not in root_to_id:
            root_to_id[root] = len(root_to_id)
        assignment[name] = root_to_id[root]
    return assignment
