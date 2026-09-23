# Regime / State 条件下的 WorldQuant Alpha 因子结构分析
## 1. 背景与分析目标

当前 Alpha 因子由 WorldQuant 风格公式计算得到，并经过横截面打分及 Beta 剥离。这里的 Beta 剥离可以理解为：对原始 Alpha 暴露做 OLS 回归，使用回归残差作为更接近 idiosyncratic alpha 的信号，从而尽可能去除公共市场因子或其它指定 Beta 暴露。

本报告进一步分析不同市场 regime / state 下候选 Alpha 之间的相关结构，目标不是重新判断 Alpha 的绝对收益能力，而是回答：

- 在某个 state 下，哪些 Alpha 提供的**边际信息最独立**；
- 哪些 Alpha 实际上属于同一信息簇，存在明显冗余；
- 在已经通过上游 scoring / filtering 的候选因子中，怎样构造一个更低冗余的 state-specific factor basket；
- 哪些 state 的统计样本不足，需要降低结论置信度。

> **重要限制：** 当前输入文件是 `regime_factor_correlation_pairs`，核心数据是候选因子之间的两两相关性，而不是 IC、Rank IC、PnL、Sharpe 或未来收益回归系数。因此本文中的“适合”主要指**适合作为组合中的独立信息源 / diversifier**，不能单凭本文件推导“该因子在该 state 下最赚钱”。最终选因子仍应与 state-conditioned IC、ICIR、turnover、capacity、PnL 等指标联合判断。
## 2. 判定逻辑
本报告主要使用以下统计量：

- `corr_mean`：某一 state 内两个 Alpha 的平均相关系数；
- `abs_corr_mean`：平均相关性的绝对值，用于衡量信息重叠程度；
- `corr_std`：相关性的时间稳定程度；
- `samples`：该 pair 的有效样本数量；
- `high_correlation`：上游规则判定的高相关 pair；
- `low_sample`：样本是否不足。

组合构造时，可以把 Alpha 看成图中的节点，把 `abs_corr_mean` 看成节点之间的边权。边权越低，两个 Alpha 的信息越独立。

本文采用以下经验解释：

- `|corr| < 0.20`：较强的独立 / diversification 价值；
- `0.20 <= |corr| < 0.40`：中低相关，可以共同使用；
- `0.40 <= |corr| < 0.60`：存在明显信息重叠；
- `|corr| >= 0.60`：高度冗余，通常更适合二选一，而不是同时给予大权重。

这些阈值只是用于组织当前结果，不应替代真实的策略验证。
## 3. 总体结论
从所有 state 的相关结构中，可以看到几个非常稳定的模式：

1. **`alpha088` 是最稳定的通用 diversifier。**  
   在绝大多数 state 下，它与其它候选 Alpha 的平均绝对相关都只有约 `0.15 ~ 0.20`，明显低于其它常规因子。因此如果它本身的 IC / PnL 不差，它非常适合作为多状态组合的基础独立因子。

2. **`alpha013` 与 `alpha016` 是最稳定的高冗余组合。**  
   多数 state 下二者相关性约 `0.68 ~ 0.72`。这说明即使经过 Beta neutralization，它们依旧保留了很强的共同结构。组合层面通常无需同时给予高权重。

3. **`alpha015` 往往与 `alpha016` 同属一个相关簇。**  
   在 dispersion-high、dispersion-normal、liquidity-starved、trend-neutral、volatility-low 等状态下，两者相关性约 `0.65 ~ 0.67`。因此 `013 / 015 / 016` 很多时候可以视为一个较大的同族信号簇。

4. **`alpha044` 是 normal / bear 类状态下较好的第二层 diversifier。**  
   它没有 `alpha088` 那么独立，但在 dispersion-low/normal、liquidity-normal、trend-bear、volatility-normal 中普遍比 013/016/050 更低相关。

5. **部分 Alpha 具有明显的 state-specific 价值。**
   - `alpha053` 在 `liquidity = high` 下几乎与其它候选正交；
   - `alpha038` 在 `liquidity = starved` 下也几乎与其它候选正交；
   - `alpha027` 更常见于 bear / high-vol / high-liquidity 状态，但与 `alpha050` 有一定重叠。

6. **`trend = bull` 的结论可信度显著偏低。**  
   该状态所有 pair 只有 `54` 个样本，并被统一标记为 `low_sample = True`。因此这里观察到的低相关结构更适合记录为研究假设，而不宜直接用于生产权重配置。
## 4. 各 State 的因子建议总表
| Dimension | State | 建议低冗余候选组合 | 主要判断 |
|---|---|---|---|
| `trend` | `bear` | `alpha088` + `alpha044` + `alpha027` | 熊市状态下 alpha088 最独立，alpha044 也较稳定；alpha027 可保留，但它与 alpha050 的相关性约 0.56，二者更适合作为替代而非并列核心。 |
| `trend` | `neutral` | `alpha088` + `alpha050` + `alpha013` | alpha088 明显承担独立信息；alpha013/016 高度重合，alpha015 也与 alpha016 较高相关。核心组合应避免同时堆叠 013/015/016。 |
| `trend` | `bull` | `alpha088` + `alpha003` + `alpha068` | 表面上这些因子互相相关性较低，但样本只有 54，全部被标记为 low_sample。此 state 应视为探索性结果，不能按其它 state 的置信度使用。 |
| `volatility` | `low` | `alpha088` + `alpha050` + `alpha013` | 低波动下 alpha088 最独立。alpha013/015/016 形成较明显的相关簇，组合里建议只取其中一个代表。 |
| `volatility` | `normal` | `alpha088` + `alpha044` + `alpha050` | 与 dispersion/liquidity 的 normal state 高度一致：088 + 044 + 050 是较自然的低冗余候选组合。 |
| `volatility` | `high` | `alpha088` + `alpha027` + `alpha013` | 高波动下 alpha088 仍是最稳的 diversifier。alpha027 与 alpha050 形成较强相关，alpha013 与 alpha016 形成更强相关，分别选一侧即可。 |
| `liquidity` | `starved` | `alpha038` + `alpha050` + `alpha013` | alpha038 与其余因子平均绝对相关仅约 0.06，是非常强的结构性 diversifier。alpha013 与 alpha016 高相关，保留其一即可。 |
| `liquidity` | `normal` | `alpha088` + `alpha044` + `alpha050` | 典型常态结构：alpha088 最独立，alpha044 次之，alpha050 可作为补充；alpha013/016 是明显同族信息。 |
| `liquidity` | `high` | `alpha053` + `alpha088` + `alpha027` | alpha053 与其余候选几乎正交，是该 state 最突出的专属 diversifier；alpha088 也保持较低相关。alpha027 与 alpha050 相关较高，不宜同时给大权重。 |
| `dispersion` | `low` | `alpha088` + `alpha044` + `alpha050` | alpha088、alpha044 的独立性最好；alpha050 可补充第三条信息。alpha013/016 仍形成明显冗余簇。 |
| `dispersion` | `normal` | `alpha088` + `alpha044` + `alpha050` | 结构与 low dispersion 很接近。alpha088 是稳定 diversifier，alpha044 次之；alpha016 与 alpha015 相关性较高。 |
| `dispersion` | `high` | `alpha088` + `alpha050` + `alpha013` | alpha088 是最明显的去相关因子；alpha050 可作为第二条信息轴。alpha013 与 alpha016 高度相关，二者通常不应同时重仓保留。 |

## 5. State-by-State 详细分析
### 5.1 `trend = bear`
**建议优先研究的低冗余组合：** `alpha088` + `alpha044` + `alpha027`

熊市状态下 alpha088 最独立，alpha044 也较稳定；alpha027 可保留，但它与 alpha050 的相关性约 0.56，二者更适合作为替代而非并列核心。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.156 | 0.180 | 854 | 强 diversifier |
| `alpha044` | 0.238 | 0.336 | 858 | 中等独立性 |
| `alpha027` | 0.333 | 0.564 | 858 | 存在一定重叠 |
| `alpha016` | 0.345 | 0.442 | 858 | 存在一定重叠 |
| `alpha050` | 0.353 | 0.564 | 854 | 存在一定重叠 |

**该 state 下最值得注意的相关关系：**

- `alpha050` ↔ `alpha027`: corr = `0.564`, samples = `858`。
- `alpha016` ↔ `alpha027`: corr = `0.442`, samples = `863`。
- `alpha016` ↔ `alpha050`: corr = `0.432`, samples = `858`。

### 5.2 `trend = neutral`
**建议优先研究的低冗余组合：** `alpha088` + `alpha050` + `alpha013`

alpha088 明显承担独立信息；alpha013/016 高度重合，alpha015 也与 alpha016 较高相关。核心组合应避免同时堆叠 013/015/016。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.195 | 0.208 | 1276 | 强 diversifier |
| `alpha050` | 0.363 | 0.441 | 1281 | 存在一定重叠 |
| `alpha015` | 0.432 | 0.665 | 1276 | 整体冗余偏高 |
| `alpha013` | 0.443 | 0.719 | 1293 | 整体冗余偏高 |
| `alpha016` | 0.508 | 0.719 | 1293 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.719`, samples = `1413`，**high_correlation**。
- `alpha016` ↔ `alpha015`: corr = `0.665`, samples = `1293`。
- `alpha013` ↔ `alpha015`: corr = `0.463`, samples = `1293`。

### 5.3 `trend = bull`
**建议优先研究的低冗余组合：** `alpha088` + `alpha003` + `alpha068`

表面上这些因子互相相关性较低，但样本只有 54，全部被标记为 low_sample。此 state 应视为探索性结果，不能按其它 state 的置信度使用。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.088 | 0.127 | 54 | 样本不足，暂不下强结论 |
| `alpha003` | 0.104 | 0.117 | 54 | 样本不足，暂不下强结论 |
| `alpha068` | 0.179 | 0.341 | 54 | 样本不足，暂不下强结论 |
| `alpha054` | 0.206 | 0.379 | 54 | 样本不足，暂不下强结论 |
| `alpha010` | 0.220 | 0.379 | 54 | 样本不足，暂不下强结论 |

**该 state 下最值得注意的相关关系：**

- `alpha054` ↔ `alpha010`: corr = `0.379`, samples = `54`，**低样本**。
- `alpha010` ↔ `alpha068`: corr = `0.341`, samples = `54`，**低样本**。
- `alpha054` ↔ `alpha068`: corr = `0.224`, samples = `54`，**低样本**。

### 5.4 `volatility = low`
**建议优先研究的低冗余组合：** `alpha088` + `alpha050` + `alpha013`

低波动下 alpha088 最独立。alpha013/015/016 形成较明显的相关簇，组合里建议只取其中一个代表。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.195 | 0.211 | 740 | 强 diversifier |
| `alpha050` | 0.372 | 0.441 | 740 | 存在一定重叠 |
| `alpha013` | 0.432 | 0.687 | 746 | 整体冗余偏高 |
| `alpha015` | 0.438 | 0.673 | 740 | 整体冗余偏高 |
| `alpha016` | 0.500 | 0.687 | 746 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.687`, samples = `813`。
- `alpha016` ↔ `alpha015`: corr = `0.673`, samples = `746`。
- `alpha013` ↔ `alpha015`: corr = `0.457`, samples = `746`。

### 5.5 `volatility = normal`
**建议优先研究的低冗余组合：** `alpha088` + `alpha044` + `alpha050`

与 dispersion/liquidity 的 normal state 高度一致：088 + 044 + 050 是较自然的低冗余候选组合。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.182 | 0.199 | 668 | 强 diversifier |
| `alpha044` | 0.260 | 0.350 | 669 | 中等独立性 |
| `alpha050` | 0.316 | 0.444 | 668 | 中等独立性 |
| `alpha013` | 0.393 | 0.695 | 669 | 存在一定重叠 |
| `alpha016` | 0.422 | 0.695 | 669 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.695`, samples = `693`。
- `alpha016` ↔ `alpha050`: corr = `0.444`, samples = `669`。
- `alpha050` ↔ `alpha013`: corr = `0.402`, samples = `669`。

### 5.6 `volatility = high`
**建议优先研究的低冗余组合：** `alpha088` + `alpha027` + `alpha013`

高波动下 alpha088 仍是最稳的 diversifier。alpha027 与 alpha050 形成较强相关，alpha013 与 alpha016 形成更强相关，分别选一侧即可。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.160 | 0.192 | 803 | 强 diversifier |
| `alpha027` | 0.379 | 0.549 | 812 | 存在一定重叠 |
| `alpha050` | 0.391 | 0.549 | 803 | 存在一定重叠 |
| `alpha013` | 0.423 | 0.706 | 812 | 整体冗余偏高 |
| `alpha016` | 0.443 | 0.706 | 812 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.706`, samples = `839`，**high_correlation**。
- `alpha050` ↔ `alpha027`: corr = `0.549`, samples = `812`。
- `alpha016` ↔ `alpha027`: corr = `0.445`, samples = `824`。

### 5.7 `liquidity = starved`
**建议优先研究的低冗余组合：** `alpha038` + `alpha050` + `alpha013`

alpha038 与其余因子平均绝对相关仅约 0.06，是非常强的结构性 diversifier。alpha013 与 alpha016 高相关，保留其一即可。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha038` | 0.062 | 0.066 | 516 | 极强 diversifier |
| `alpha050` | 0.331 | 0.442 | 513 | 存在一定重叠 |
| `alpha015` | 0.399 | 0.669 | 513 | 存在一定重叠 |
| `alpha013` | 0.402 | 0.697 | 516 | 存在一定重叠 |
| `alpha016` | 0.468 | 0.697 | 516 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.697`, samples = `559`。
- `alpha016` ↔ `alpha015`: corr = `0.669`, samples = `516`。
- `alpha015` ↔ `alpha013`: corr = `0.450`, samples = `516`。

### 5.8 `liquidity = normal`
**建议优先研究的低冗余组合：** `alpha088` + `alpha044` + `alpha050`

典型常态结构：alpha088 最独立，alpha044 次之，alpha050 可作为补充；alpha013/016 是明显同族信息。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.185 | 0.199 | 1081 | 强 diversifier |
| `alpha044` | 0.267 | 0.359 | 1088 | 中等独立性 |
| `alpha050` | 0.318 | 0.440 | 1081 | 中等独立性 |
| `alpha013` | 0.398 | 0.695 | 1088 | 存在一定重叠 |
| `alpha016` | 0.423 | 0.695 | 1088 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.695`, samples = `1125`。
- `alpha016` ↔ `alpha050`: corr = `0.440`, samples = `1088`。
- `alpha013` ↔ `alpha050`: corr = `0.407`, samples = `1088`。

### 5.9 `liquidity = high`
**建议优先研究的低冗余组合：** `alpha053` + `alpha088` + `alpha027`

alpha053 与其余候选几乎正交，是该 state 最突出的专属 diversifier；alpha088 也保持较低相关。alpha027 与 alpha050 相关较高，不宜同时给大权重。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha053` | 0.010 | 0.014 | 632 | 极强 diversifier |
| `alpha088` | 0.126 | 0.196 | 631 | 强 diversifier |
| `alpha016` | 0.272 | 0.454 | 632 | 中等独立性 |
| `alpha027` | 0.283 | 0.554 | 632 | 中等独立性 |
| `alpha050` | 0.297 | 0.554 | 631 | 中等独立性 |

**该 state 下最值得注意的相关关系：**

- `alpha050` ↔ `alpha027`: corr = `0.554`, samples = `632`。
- `alpha016` ↔ `alpha027`: corr = `0.454`, samples = `639`。
- `alpha050` ↔ `alpha016`: corr = `0.430`, samples = `632`。

### 5.10 `dispersion = low`
**建议优先研究的低冗余组合：** `alpha088` + `alpha044` + `alpha050`

alpha088、alpha044 的独立性最好；alpha050 可补充第三条信息。alpha013/016 仍形成明显冗余簇。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.179 | 0.199 | 652 | 强 diversifier |
| `alpha044` | 0.258 | 0.349 | 656 | 中等独立性 |
| `alpha050` | 0.318 | 0.449 | 652 | 中等独立性 |
| `alpha013` | 0.389 | 0.679 | 656 | 存在一定重叠 |
| `alpha016` | 0.419 | 0.679 | 656 | 存在一定重叠 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.679`, samples = `679`。
- `alpha016` ↔ `alpha050`: corr = `0.449`, samples = `656`。
- `alpha013` ↔ `alpha050`: corr = `0.404`, samples = `656`。

### 5.11 `dispersion = normal`
**建议优先研究的低冗余组合：** `alpha088` + `alpha044` + `alpha050`

结构与 low dispersion 很接近。alpha088 是稳定 diversifier，alpha044 次之；alpha016 与 alpha015 相关性较高。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.184 | 0.197 | 839 | 强 diversifier |
| `alpha044` | 0.268 | 0.354 | 850 | 中等独立性 |
| `alpha050` | 0.314 | 0.431 | 844 | 中等独立性 |
| `alpha015` | 0.392 | 0.659 | 839 | 存在一定重叠 |
| `alpha016` | 0.410 | 0.659 | 850 | 存在一定重叠 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha015`: corr = `0.659`, samples = `850`。
- `alpha016` ↔ `alpha050`: corr = `0.431`, samples = `883`。
- `alpha050` ↔ `alpha015`: corr = `0.394`, samples = `844`。

### 5.12 `dispersion = high`
**建议优先研究的低冗余组合：** `alpha088` + `alpha050` + `alpha013`

alpha088 是最明显的去相关因子；alpha050 可作为第二条信息轴。alpha013 与 alpha016 高度相关，二者通常不应同时重仓保留。

| Factor | 与其它候选平均 `|corr|` | 最大 `|corr|` | 最小样本数 | 解读 |
|---|---:|---:|---:|---|
| `alpha088` | 0.185 | 0.199 | 676 | 强 diversifier |
| `alpha050` | 0.364 | 0.436 | 682 | 存在一定重叠 |
| `alpha015` | 0.423 | 0.656 | 676 | 整体冗余偏高 |
| `alpha013` | 0.435 | 0.709 | 685 | 整体冗余偏高 |
| `alpha016` | 0.499 | 0.709 | 685 | 整体冗余偏高 |

**该 state 下最值得注意的相关关系：**

- `alpha016` ↔ `alpha013`: corr = `0.709`, samples = `739`，**high_correlation**。
- `alpha016` ↔ `alpha015`: corr = `0.656`, samples = `685`。
- `alpha013` ↔ `alpha015`: corr = `0.449`, samples = `685`。

## 6. 可以抽象出的 Alpha 因子簇

### 6.1 `alpha013 / alpha015 / alpha016`：高重叠簇

这三个 Alpha 在多个 state 中反复出现较高相关，尤其：

- `alpha013 ↔ alpha016` 多次达到约 `0.69 ~ 0.72`；
- `alpha015 ↔ alpha016` 多次达到约 `0.65 ~ 0.67`。

因此在组合层面，更合理的处理通常不是把三个信号简单相加，而是：

1. 在每个 state 内比较它们各自的 IC / ICIR / PnL；
2. 选其中最强者作为该簇代表；
3. 或对该簇内部再次做 PCA / residualization；
4. 或在优化器中显式加入 correlation penalty / group exposure constraint。

### 6.2 `alpha088`：通用独立信息轴

`alpha088` 在几乎所有主流 state 中都保持较低相关，是当前结果中最稳定的独立信息来源。

这意味着它很适合作为一个 **cross-regime anchor factor**：  
不是因为相关性低就自动说明它有收益，而是如果它已经通过上游 alpha quality filter，那么它被其它因子替代的可能性较低。

### 6.3 `alpha044`：常态 / 熊市的辅助信息轴

`alpha044` 在以下状态中表现出较好的独立性：

- dispersion = low / normal
- liquidity = normal
- trend = bear
- volatility = normal

因此它更像是一个在“非极端状态”下用于补充 alpha088 的第二层结构因子。

### 6.4 `alpha053`：High Liquidity 专属候选

在 `liquidity = high` 下：

- alpha053 ↔ alpha050 ≈ `-0.014`
- alpha053 ↔ alpha027 ≈ `-0.011`
- alpha053 ↔ alpha016 ≈ `-0.009`
- alpha053 ↔ alpha088 ≈ `0.004`

几乎可以视为正交信号。

如果它在 high-liquidity state 下同时具有稳定正 IC，那么它是非常值得保留的 regime-specialist factor。

### 6.5 `alpha038`：Liquidity Starved 专属候选

在 `liquidity = starved` 下，`alpha038` 与其它候选的相关性仅约 `0.05 ~ 0.07`。

其结构和 high-liquidity 下的 alpha053 很类似：它并非一个普遍出现的 Alpha，但在特定状态下提供非常独立的信息。

### 6.6 `alpha027` 与 `alpha050`

两者在多个偏极端状态下同时出现，但也存在明显重叠：

- liquidity = high：约 `0.554`
- trend = bear：约 `0.564`
- volatility = high：约 `0.549`

因此两者在这些 state 下通常更适合作为竞争关系：  
根据 IC / turnover / capacity / PnL 选择其中一个，或者降低共同权重，而不是把它们视为完全独立的两条 alpha。
## 7. 建议的 State-Specific 因子框架

如果上游已经用预测能力指标筛出候选 Alpha，那么可以把当前相关性分析作为第二层组合过滤器：

```text
Raw WorldQuant Alphas
        |
        v
Cross-sectional scoring / normalization
        |
        v
Beta neutralization via OLS residual
        |
        v
Regime-conditioned alpha quality filter
(IC / RankIC / ICIR / forward return / t-stat)
        |
        v
Correlation clustering within each state
        |
        +--> remove redundant factors
        |
        +--> preserve state-specific diversifiers
        |
        v
State-specific factor basket
        |
        v
Weight optimization
(IC strength + stability + turnover + correlation penalty)
```

一个比较实用的 state-conditioned 权重目标可以写成：

```text
score_i(state)
    = IC_zscore_i
    + λ1 * ICIR_zscore_i
    - λ2 * turnover_zscore_i
    - λ3 * redundancy_i
```

其中：

```text
redundancy_i
    = mean_j |corr(alpha_i, alpha_j)|
```

这样，相关性不再负责决定“Alpha 有没有预测能力”，而只负责决定“已经有效的 Alpha 之间有多少重复信息”。
## 8. 当前结果对应的第一版 Factor Map

可以把当前结果压缩成下面的研究地图：

```text
                    ┌───────────────────────┐
                    │   Cross-regime Core   │
                    │       alpha088        │
                    └───────────┬───────────┘
                                │
          ┌─────────────────────┼─────────────────────┐
          │                     │                     │
          v                     v                     v
  Normal / Bear           High Liquidity       Liquidity Starved
     alpha044               alpha053               alpha038
          │                     │                     │
          v                     v                     v
  alpha050 / cluster      alpha027 / 050       alpha050 + one of
  representative          choose carefully      013/015/016

Common redundant cluster:
    alpha013
       ↕ high corr
    alpha016
       ↕ high corr
    alpha015
```

因此，当前最值得进一步验证的不是简单地“哪个 Alpha 排名第一”，而是：

- `alpha088` 是否在大多数 state 都同时保持正 IC；
- `alpha053` 是否真正只在 high-liquidity 状态产生预测力；
- `alpha038` 是否真正只在 liquidity-starved 状态产生预测力；
- `alpha044` 是否是 normal / bear 的稳定辅助因子；
- `013 / 015 / 016` 这个高相关簇中，各 state 到底应该留下哪一个代表；
- `027` 和 `050` 在 bear / high-vol / high-liquidity 下谁的风险调整后收益更好。
## 9. 下一步最应该补充的数据

要从“相关结构分析”升级成真正的 **state-conditioned factor selection**，建议把每个 `(dimension, state, alpha)` 再补充以下字段：

```text
samples
mean_ic
rank_ic
ic_std
icir
positive_ic_ratio
forward_return_mean
forward_return_tstat
turnover
max_drawdown
long_short_sharpe
capacity_proxy
```

之后就可以把本报告中的“独立性”与“有效性”合并：

```text
Good State Factor
    = Predictive
    + Stable
    + Low Redundancy
    + Tradable
```

真正的目标不是找到最低相关的 Alpha，而是找到：

> **在指定 state 下具有稳定预测能力，同时又不能被其它 Alpha 轻易替代的信息源。**
