"""训练目标：逐期截面 IC 序列的 IC_IR（均值 / 标准差），作为 LightGBM 的自定义损失和早停指标。

损失 = −IC_IR。每一期（一根 bar）的 IC 是**加权 Pearson 相关**：

- 预测值 vs 标签（标签已经在训练集构建时做了截面排名，所以接近 RankIC，但处处可导——Spearman 要先排名，
  排名的梯度为 0，没法直接反向传播，ML_ALPHA_DESIGN.md §5.1）；
- 只在**损失掩码**内的 symbol 上算（可流通性掩码，训练集构建时已经把掩码外的行去掉了）；
- **首尾加权**（`tail_weight`）：标签排名在首尾 `tail_quantile` 里的行权重更大。实盘只交易 Top-K / Last-K 两端，
  中间排得准不准对收益没有影响（§5.3）。权重按**标签**排名给、训练中固定不变：按预测值排名给权重的话，训练初期
  预测值几乎相同，权重等于随机。

梯度（第 g 期、行 i，权重 w 在期内归一，p̄ / ȳ 为加权均值，v_p / v_y 为加权方差）：

    IC_g = Σ w (p − p̄)(y − ȳ) / sqrt(v_p · v_y)
    ∂IC_g / ∂p_i = w_i · [ (y_i − ȳ) / sqrt(v_p · v_y) − IC_g · (p_i − p̄) / v_p ]
    IR = m / s（m、s 为各期 IC 的均值、总体标准差，G 期）
    ∂IR / ∂IC_g = 1 / (G·s) − m · (IC_g − m) / (G · s³)

LightGBM 的自定义损失要给二阶导，这里给常数 1，并把梯度整体缩放到均方根为 1（归一化梯度下降）：IC 对预测值的
尺度不敏感，梯度的绝对大小没有意义，只有方向有用；缩放后学习率的含义每一轮都一致。

行必须按时间排好序、同一期的行连续（训练集构建保证），期的边界由 `starts` 给出。
"""

from __future__ import annotations

import numpy as np

EPS = 1e-12


def period_starts(times: np.ndarray) -> np.ndarray:
    """按时间排好序的行 -> 每一期第一行的下标。"""
    times = np.asarray(times)
    if len(times) == 0:
        return np.zeros(0, dtype=np.int64)
    change = np.flatnonzero(times[1:] != times[:-1]) + 1
    return np.concatenate([[0], change]).astype(np.int64)


class ICIRObjective:
    """一份数据集（训练集或内部验证集）上的 IC_IR：`loss()` / `gradient()` / LightGBM 回调都从这里来。

    行数少于 `min_period_rows` 或标签整期恒定的期不参与（不计 IC、梯度为 0）。
    """

    def __init__(self, y: np.ndarray, weights: np.ndarray, starts: np.ndarray, *, min_period_rows: int = 10):
        self.y = np.asarray(y, dtype="float64")
        self.starts = np.asarray(starts, dtype=np.int64)
        n = len(self.y)
        sizes = np.diff(np.append(self.starts, n))
        self.group = np.repeat(np.arange(len(self.starts)), sizes)

        w = np.asarray(weights, dtype="float64")
        wsum = np.add.reduceat(w, self.starts)
        self.w = w / wsum[self.group]
        self.y_mean = np.add.reduceat(self.w * self.y, self.starts)
        self.dy = self.y - self.y_mean[self.group]
        self.vy = np.add.reduceat(self.w * self.dy**2, self.starts)
        self.valid = (sizes >= min_period_rows) & (self.vy > EPS)
        if not self.valid.any():
            raise ValueError("没有一期满足条件（行数足够且标签不恒定），无法计算 IC_IR")

    def _period_stats(self, p: np.ndarray):
        p = np.asarray(p, dtype="float64")
        p_mean = np.add.reduceat(self.w * p, self.starts)
        dp = p - p_mean[self.group]
        cov = np.add.reduceat(self.w * dp * self.dy, self.starts)
        vp = np.add.reduceat(self.w * dp**2, self.starts)
        ic = cov / np.sqrt((vp + EPS) * self.vy + EPS)
        return dp, vp, ic

    def ic_series(self, p: np.ndarray) -> np.ndarray:
        """每一期的加权 IC（不参与的期为 NaN）。"""
        _, _, ic = self._period_stats(p)
        return np.where(self.valid, ic, np.nan)

    def ic_ir(self, p: np.ndarray) -> float:
        ic = self.ic_series(p)[self.valid]
        std = ic.std()
        return float(ic.mean() / std) if std > EPS else 0.0

    def gradient(self, p: np.ndarray) -> np.ndarray:
        """损失 −IC_IR 对每行预测值的梯度（未缩放）。"""
        dp, vp, ic = self._period_stats(p)
        ic_v = ic[self.valid]
        g = len(ic_v)
        m = ic_v.mean()
        s = np.sqrt(ic_v.var() + EPS)
        d_ir = np.zeros(len(ic))
        d_ir[self.valid] = 1.0 / (g * s) - m * (ic_v - m) / (g * s**3)

        root = np.sqrt((vp + EPS) * self.vy + EPS)
        d_ic = self.w * (self.dy / root[self.group] - ic[self.group] * dp / (vp[self.group] + EPS))
        return -d_ir[self.group] * d_ic

    # ---- LightGBM 回调 ----

    def lgb_objective(self, preds: np.ndarray, _dataset) -> tuple[np.ndarray, np.ndarray]:
        grad = self.gradient(preds)
        scale = np.sqrt(np.mean(grad**2))
        if scale > 0:
            grad = grad / scale
        return grad, np.ones_like(grad)

    def lgb_metric(self, preds: np.ndarray, _dataset) -> tuple[str, float, bool]:
        return "ic_ir", self.ic_ir(preds), True


def tail_weights(label_rank: np.ndarray, *, tail_quantile: float, tail_weight: float) -> np.ndarray:
    """`label_rank` 是期内截面百分位排名（平移到 [-0.5, 0.5]）；首尾 `tail_quantile` 内的行权重 `tail_weight`，其余 1。"""
    tail = np.abs(np.asarray(label_rank, dtype="float64")) >= 0.5 - tail_quantile
    return np.where(tail, tail_weight, 1.0)
