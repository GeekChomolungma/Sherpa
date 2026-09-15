# Sherpa 数据接入层：数据结构与转换流水线

金融面板数据的本质是一个 三维张量（3D Tensor）：Time（时间轴） × Asset/Symbol（资产标的轴） × Feature/Field（特征字段：OHLCV等）

## 0. 三种主流内存数据结构形态形态内存表现形式适用场景优势与劣势
1. 字典矩阵流（Dict of 2D DataFrames）{'close': df_close, 'open': df_open, ...}每个 DataFrame 行是 Time，列是 Symbol。世坤 101 等截面 Alpha 因子批量回测（极力推荐）优：完美契合公式向量化。比如算截面 rank 只需要 df_close.pct_change().rank(axis=1)。劣：如果只有单币种策略，这种做法显得冗余。
2. 展平长表（Long-form DataFrame）复合索引（start_time, symbol）作为 MultiIndex，后接 open, high, low, close, volume 列。ClickHouse 批量读出后初步载入，或使用 Polars 做并行计算优：与 ClickHouse 的扁平行记录天然对齐；Polars 处理几千万行长表速度极快。  劣：做复杂的跨资产截面算子（如截面中性化、行业暴露对比）时需要频繁 pivot，有转换开销。
3. 3D 张量（NumPy 3D Array / PyTorch Tensor）形状为 (n_time, n_symbols, n_features) 的纯连续内存数组。高频截面打分、量化深度学习/ML 因子计算优：零对象开销，SIMD 矢量计算性能天花板。劣：丢失了字符串 symbol 和 Datetime 的原生索引，需要业务外壳维护 index 映射字典。

---

本文档说明 `sherpa.data` 模块的数据结构规范，重点展示从 **ClickHouse 扁平长表** 经由 **`ch_long_to_panel`** 转换为 **`BarPanel`（宽表面板容器）** 的过程，以及最终打包给策略消费的 **`MarketEvent`** 信封。

以下以 **`BTCUSDT`、`ETHUSDT`、`SOLUSDT`** 三个币种在连续 3 个 4h 截面上的数据作为贯穿示例。

---

## 1. 数据流转概览

```mermaid
flowchart LR
    A["ClickHouse 表<br/>market.fapi_kline_4h"] -->|"fetch_history()"| B["长表 DataFrame<br/>(M 行 × 11 列)"]
    B -->|"ch_long_to_panel()"| C["BarPanel<br/>9 张 (T, N) 宽表 + coverage"]
    C -->|"HistoricalPanelSource / LivePanelSource"| D["MarketEvent<br/>(截面事件信封)"]
```

---

## 2. 输入结构：ClickHouse 扁平长表 (`CHReader.fetch_history`)

[`CHReader.fetch_history`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/ch_reader.py#L33-L76) 从 ClickHouse 查询并返回标准的二维扁平长表（Long-form DataFrame）：
* **行数 $M$**：各 symbol 的 K 线记录数总和。
* **索引（Index）**：整数序列 `RangeIndex(0, 1, 2, ...)`，按 `start_time` 升序排列。
* **列名（Columns）**：固定 11 列（`symbol`、`start_time` 以及 9 个行情数值列）。

### 三币输入长表示例（BTC, ETH, SOL - 4h 周期）

| index | symbol | start_time | open | high | low | close | volume | quote_volume | taker_buy_volume | taker_buy_quote_volume | trades_count |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| 0 | BTCUSDT | 2026-01-01 00:00:00 | 95000.0 | 95500.0 | 94800.0 | 95200.0 | 120.5 | 11471600.0 | 62.1 | 5911920.0 | 45000 |
| 1 | ETHUSDT | 2026-01-01 00:00:00 | 3200.0 | 3250.0 | 3180.0 | 3220.0 | 850.0 | 2737000.0 | 410.0 | 1320200.0 | 28000 |
| 2 | SOLUSDT | 2026-01-01 00:00:00 | 185.0 | 188.0 | 183.5 | 186.2 | 4200.0 | 782040.0 | 2150.0 | 400330.0 | 16000 |
| 3 | BTCUSDT | 2026-01-01 04:00:00 | 95200.0 | 96000.0 | 95100.0 | 95800.0 | 140.2 | 13431160.0 | 75.3 | 7213740.0 | 51000 |
| 4 | ETHUSDT | 2026-01-01 04:00:00 | 3220.0 | 3280.0 | 3210.0 | 3250.0 | 920.0 | 2990000.0 | 480.0 | 1560000.0 | 31000 |
| 5 | SOLUSDT | 2026-01-01 04:00:00 | 186.2 | 189.5 | 185.0 | 187.8 | 4600.0 | 863880.0 | 2300.0 | 431940.0 | 18500 |
| 6 | BTCUSDT | 2026-01-01 08:00:00 | 95800.0 | 96200.0 | 94900.0 | 95100.0 | 165.0 | 15691500.0 | 70.2 | 6676020.0 | 58000 |
| 7 | ETHUSDT | 2026-01-01 08:00:00 | 3250.0 | 3260.0 | 3190.0 | 3210.0 | 890.0 | 2856900.0 | 420.0 | 1348200.0 | 29000 |
| 8 | SOLUSDT | 2026-01-01 08:00:00 | 187.8 | 191.0 | 186.0 | 189.5 | 5100.0 | 966450.0 | 2700.0 | 511650.0 | 21000 |

*(注：在实时 1m 场景下，上游 Redis `kline:{SYM}:1m` 为包含这 10 个字段的紧凑列表，由 `redis_window_to_panel` 走相同逻辑转为宽表)*

---

## 3. 转换与核心容器：`ch_long_to_panel` $\to$ `BarPanel`

[`ch_long_to_panel`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/normalizer.py#L77-L107) 将上述长表转换为多资产宽表面板 [`BarPanel`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/schema.py#L57-L138)。

### 3.1 转换处理规则
1. **时区归一化**：`start_time` 统一转换为 UTC 时区的 `pandas.DatetimeIndex`。
2. **多字段转置（Pivot）**：对 9 个行情字段分别执行转置：
   ```python
   pivoted = df.pivot(index="start_time", columns="symbol", values=field_name)
   ```
   *若查询忘记加 `FINAL` 导致存在重复的 `(symbol, start_time)`，`pivot` 会在此处报错拦截。*
3. **网格对齐与缺失填充**：通过 `.reindex(columns=symbols_final)` 确保各表的列顺序严格一致。**缺失值填为 `NaN`，坚决不作 `ffill` 前向填充**。
4. **计算覆盖率**：根据 `panel.close` 逐行统计有效 symbol 占 Universe 总数的比例，生成 `panel.coverage`。

### 3.2 转换后的 `BarPanel` 结构与示例

`BarPanel` 是不可变数据类，包含元数据及 9 张同构的 $(T, N)$ 宽表 DataFrame：

```python
# BarPanel 属性签名
panel.interval   # '4h'
panel.symbols    # ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
panel.open       # pd.DataFrame(shape=(3, 3))
panel.high       # pd.DataFrame(shape=(3, 3))
panel.low        # pd.DataFrame(shape=(3, 3))
panel.close      # pd.DataFrame(shape=(3, 3))
panel.volume     # pd.DataFrame(shape=(3, 3))
...              # quote_volume, taker_buy_volume, taker_buy_quote_volume, trades_count
panel.coverage   # pd.Series(shape=(3,))
```

#### 输出示例 1：`panel.close`（收盘价宽表，$(3 \times 3)$）
* **Index (行)**：UTC `start_time`
* **Columns (列)**：标的代码

| start_time (UTC) | BTCUSDT | ETHUSDT | SOLUSDT |
| :--- | :---: | :---: | :---: |
| **2026-01-01 00:00:00+00:00** | 95200.0 | 3220.0 | 186.2 |
| **2026-01-01 04:00:00+00:00** | 95800.0 | 3250.0 | 187.8 |
| **2026-01-01 08:00:00+00:00** | 95100.0 | 3210.0 | 189.5 |

#### 输出示例 2：`panel.volume`（成交量宽表，$(3 \times 3)$）

| start_time (UTC) | BTCUSDT | ETHUSDT | SOLUSDT |
| :--- | :---: | :---: | :---: |
| **2026-01-01 00:00:00+00:00** | 120.5 | 850.0 | 4200.0 |
| **2026-01-01 04:00:00+00:00** | 140.2 | 920.0 | 4600.0 |
| **2026-01-01 08:00:00+00:00** | 165.0 | 890.0 | 5100.0 |

#### 输出示例 3：`panel.coverage`（覆盖率序列，$(3 \times 1)$）

| start_time (UTC) | coverage |
| :--- | :---: |
| **2026-01-01 00:00:00+00:00** | 1.000 |
| **2026-01-01 04:00:00+00:00** | 1.000 |
| **2026-01-01 08:00:00+00:00** | 1.000 |

*(注：若某一时刻某币种停盘缺数据，对应单元格填 `NaN`，该截面覆盖率即相应下降为 `2/3 ≈ 0.667`)*

---

## 4. 消费信封：`MarketEvent`

策略主循环消费的数据并非裸 `BarPanel`，而是包含时序元数据的 [`MarketEvent`](file:///d:/code-repo/Chomo/Sherpa/sherpa/data/schema.py#L149-L191) 事件信封：

```python
@dataclass(frozen=True)
class MarketEvent:
    interval: str             # "4h"
    bar_start_time: pd.Timestamp  # 2026-01-01 00:00:00+00:00
    bar_end_time: pd.Timestamp    # 2026-01-01 03:59:59.999+00:00 (严格减 1ms，对齐币安闭合惯例)
    symbols_count: int        # 当期有行情数据的 symbol 数 (如 3)
    coverage_ratio: float     # 覆盖率 (如 1.0)
    panel: BarPanel           # 截断至当前截面的历史滑动窗口切片 (如最近 200 根)
    is_cold_start: bool = False
```

### 驱动源行为
* **回测模式（`HistoricalPanelSource`）**：
  一次性拉取全历史长表并转为大 `BarPanel`，随后按时间步递增 yield 出 `MarketEvent`。每次迭代仅切片提供 `lo ~ pos` 的历史窗口，**在数据源层面确保回测不会发生前视偏差**。
* **实盘模式（`LivePanelSource`）**：
  阻塞监听 Redis `stream:market:kline_ready` 通知。1m 周期通过 `WindowCache` 在内存中维护最近 200 根增量滑动窗口并产出事件；粗周期（如 4h）现查 ClickHouse 最近 200 根生成事件。
