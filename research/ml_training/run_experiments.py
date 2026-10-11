"""ML alpha 的探索实验：一批配置（case）各自滚动训练、样本外打分，用关卡3 同口径的扣费回测比较，找盈利点。

    CH_HOST=... CH_PASSWORD=... python research/ml_training/run_experiments.py                 # 跑全部 case
    python research/ml_training/run_experiments.py --cases h6,h6_raw                            # 只跑指定的
    python research/ml_training/run_experiments.py --summary-only                               # 只重新汇总

跟正式训练（`run_training.py`）的关系：训练用的是同一套函数（`dataset.build_training_frame` / `plan_folds` /
`split_inner_validation`、`trainer.train_fold` 两步训练），只是配置不从 `config.py` 读，而是每个 case 自己给；
评估用 `evaluation.py`（关卡3 同口径的拷贝）。所以这里挑出来的配置，搬进 `config.py` / `models.py` 后走正式流水线，
结果应该一致（`v2_official` vs `v2_retrain` 两个 case 就是用来核对这一点的）。

**怎么挑配置才不自欺**：每个模型都是滚动训练的，选择段和验证段的打分都是样本外的。汇总表按**选择段**的扣费净 Sharpe
挑每个 case 的最好组合（映射 × 调仓频率 × 平滑），再报告**同一组合**在验证段的表现——验证段只用来确认，不用来挑。
holdout 全程不碰。B 组特征名单是在选择段上选出来的，选择段数字仍偏乐观。

产出（`research/alpha_research/MLalpha/experiments/`，CSV / 模型 / 缓存都不进 git）：
- `<case>/folds.csv`：每个重训时点的早停轮数、内部验证 IC_IR；
- `<case>/diagnostics.csv`：选择段 / 验证段 × 平滑：RankIC、Pearson IC、首尾价差、vol 暴露；
- `<case>/friction_grid.csv`：平滑 × 映射 × 调仓频率 × 成本 × 段的完整绩效长表；
- `<case>/scores.pkl`：样本外打分 (T, N)；`<case>/models/`：模型文件；
- `summary.csv`：每个 case 一行（按选择段挑的最好组合 + 它在验证段的表现 + 诊断）。
"""

from __future__ import annotations

import argparse
import dataclasses
import pickle
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

from sherpa.alpha.custom.ml import LgbmV1
from sherpa.alpha.custom.ml import models as ml_models
from sherpa.backtest.attribution import attribute, period_stats, style_factor_returns
from sherpa.backtest.score_backtest import cost_segment_rows, run_score_backtest, target_path
from sherpa.alpha.custom.ml.features import (
    EXTRA_SYMBOL_FEATURES, DERIVATIVES_CORE, DERIVATIVES_LS, DERIVATIVES_OI, PRICE_VOLUME_EXTRAS, FeatureSpec, build_features,
)
from sherpa.alpha.liquidity import LiquidityFilter
from sherpa.data.schema import interval_to_timedelta
from sherpa.metrics.factor import forward_returns
from sherpa.metrics.tradability import DEFAULT_LOOKBACK, SEASONING_PERIOD

import config
import evaluation
from data import END_TIME, EXECUTION_DELAY_BARS, INTERVAL, START_TIME, VALIDATION_START, load_universe_panel
from dataset import TrainingFrame, build_training_frame, plan_folds, split_inner_validation
from trainer import train_fold

OUT_DIR = Path(__file__).resolve().parents[1] / "alpha_research" / "MLalpha" / "experiments"
CACHE_DIR = OUT_DIR / "_cache"


@dataclass(frozen=True)
class Case:
    """一个实验配置。没写的项 = 正式训练当前的配置（config.py / LgbmV1.spec，2026-10-05）。"""

    name: str
    note: str
    source: str = "train"                       # "train"：本脚本滚动训练；"official:<模型类名>"：直接用正式模型（MLAlpha.compute）；
                                                # "factor:<名字>"：不用 ML，直接拿单个原始特征打分（FACTORS），方向按选择段 IC 符号定；
                                                # "blend:<case1>+<case2>+..."：几个已跑完 case 的原始预测值平均（更多种子的集成）
    neutralize_scores: tuple[str, ...] = ()     # 打分出来后，逐期截面回归剥离这些暴露再交易：可选 "vol42" / "beta" / "size"
    horizon: int = 1                            # 标签持有期（根 bar）；执行延迟固定用 research_config 的
    label_transform: str = "rank"               # "rank" / "raw_clip"
    objective: str = "ic_ir"                    # "ic_ir" / "l2_rank"
    tail_quantile: float = config.TAIL_QUANTILE
    tail_weight: float = config.TAIL_WEIGHT
    window_bars: Optional[int] = config.TRAIN_WINDOW_BARS
    valid_bars: int = config.INNER_VALID_BARS
    neutralize_label: bool = False
    drop_features: tuple[str, ...] = ()         # 按前缀去掉的特征，比如 ("alpha:",) = 不要 B 组
    extras: tuple[str, ...] = ()                # A 组可选特征（OI / 多空比 / 价量补充，features.EXTRA_SYMBOL_FEATURES 的名字）
    with_b: bool = True                         # False = 不算 B 组（世坤因子），比 drop_features=("alpha:",) 省掉计算
    # 研究窗口：取数从 research_start 起（之前的数据切掉，特征 warm-up 跟正式流水线一致），第一个模型要攒够 min_train_bars；
    # validation_start 切选择段 / 验证段。默认 = research_config.json
    research_start: str = START_TIME
    validation_start: str = VALIDATION_START
    min_train_bars: int = config.MIN_TRAIN_BARS
    min_percentile: float = 0.5                 # 流动性范围（特征排名 + 损失 + 评估）
    lgb_overrides: tuple[tuple[str, Any], ...] = ()
    seeds: tuple[int, ...] = config.SEEDS
    model: Optional[str] = None                 # 绑定的正式模型类名（`model_case` 填），特征清单直接用它的 spec

    @property
    def spec(self) -> FeatureSpec:
        if self.model is not None:
            return getattr(ml_models, self.model).spec
        return FeatureSpec(
            name="lgbm_v1", version=1, alphas=LgbmV1.spec.alphas if self.with_b else (),
            liquidity=LiquidityFilter(min_percentile=self.min_percentile, seasoning_period=SEASONING_PERIOD, lookback=DEFAULT_LOOKBACK),
            extras=self.extras,
        )


def model_case(name: str, note: str, model: str, **overrides: Any) -> Case:
    """跟正式模型（`sherpa.alpha.custom.ml.models` 里的 MLAlpha 子类）**完全相同配置**的探索 case：特征清单 = 它的 spec，
    训练配置 = `config.for_model(它的 training_overrides)`（正式训练 run_training.py 用的同一个函数）。`overrides` 只用来
    在它的基础上改一两项做对照（比如换种子），改了什么就是什么，其余跟正式模型一致。

    探索里挑出来的配置要进正式流水线，先写成 models.py 里的子类，再用这个函数跑一次核对：同一份数据上它的打分应该跟
    正式模型 `MLAlpha.compute` 的逐格相同（训练集分箱随机数固定之后，见 config.LGB_PARAMS）。
    """
    cls = getattr(ml_models, model)
    cfg = config.for_model(cls.training_overrides)
    lgb_defaults = config.LGB_PARAMS
    fields = dict(
        horizon=cfg.label_horizon_bars, label_transform=cfg.label_transform, objective=cfg.objective,
        tail_quantile=cfg.tail_quantile, tail_weight=cfg.tail_weight, window_bars=cfg.train_window_bars,
        valid_bars=cfg.inner_valid_bars, neutralize_label=cfg.neutralize_label, min_train_bars=cfg.min_train_bars,
        seeds=tuple(cfg.seeds), min_percentile=cls.spec.liquidity.min_percentile,
        extras=cls.spec.extras, with_b=bool(cls.spec.alphas),
        lgb_overrides=tuple((k, v) for k, v in cfg.lgb_params.items() if lgb_defaults.get(k) != v),
        model=model,
    )
    unsupported = {
        "retrain_every_bars": config.RETRAIN_EVERY_BARS, "refit_on_full_window": True,
        "min_period_rows": config.MIN_PERIOD_ROWS, "num_boost_round": config.NUM_BOOST_ROUND,
        "early_stopping_rounds": config.EARLY_STOPPING_ROUNDS,
    }
    differs = {k: getattr(cfg, k) for k, v in unsupported.items() if getattr(cfg, k) != v}
    if differs:
        raise ValueError(f"{model} 改了探索脚本不支持覆盖的训练配置 {differs}，先给 Case 加对应字段")
    return Case(name, note, **{**fields, **overrides})


# 单因子基线（source="factor:<名字>"）：原始值，panel -> (T, N)；方向在 evaluate 前按选择段 RankIC 的符号统一成"越大越好"
FACTORS = {
    "ret_1": lambda p: p.close.pct_change(1, fill_method=None),
    "ret_6": lambda p: p.close.pct_change(6, fill_method=None),
    "ret_42": lambda p: p.close.pct_change(42, fill_method=None),
    "ret_120": lambda p: p.close.pct_change(120, fill_method=None),
    "vol_42": lambda p: p.close.pct_change(fill_method=None).rolling(42).std(),
    "quote_volume_42": lambda p: p.quote_volume.rolling(42).mean(),
    "quote_volume_surge_6_42": lambda p: p.quote_volume.rolling(6).mean() / p.quote_volume.rolling(42).mean(),
    "taker_buy_ratio_6": lambda p: p.taker_buy_quote_volume.rolling(6).sum() / p.quote_volume.rolling(6).sum(),
    "oi_change_6": lambda p: p.open_interest.pct_change(6, fill_method=None),
    "oi_change_42": lambda p: p.open_interest.pct_change(42, fill_method=None),
    "dist_high_42": lambda p: p.close / p.high.rolling(42).max() - 1,
}

H6 = dict(horizon=6)
V2 = dict(horizon=6, label_transform="raw_clip", window_bars=None, seeds=tuple(range(9)))
W4 = dict(V2, research_start="2024-01-01", validation_start="2025-03-01", min_train_bars=6 * 120)
V4H_FINALISTS = {
    "v4h_ac": (),
    "v4h_ls": DERIVATIVES_LS,
    "v4h_ls_pv": DERIVATIVES_LS + PRICE_VOLUME_EXTRAS,
    "v4h_all": DERIVATIVES_LS + DERIVATIVES_OI + PRICE_VOLUME_EXTRAS,
}
# 第 1–7 批的产出没有保留，定义留着作记录（结论见 research/alpha_research/MLalpha/experiments/FINDINGS*.md，那里的数字是
# 早期评估口径）；要复现就 --cases 重跑，重跑的结果是当前口径。
CASES: list[Case] = [
    # ---- 基线：核对本脚本跟正式流水线一致 ----
    Case("v2_official", "正式流水线当前的模型（第二版），用来核对评估口径跟关卡3 一致", source="official:LgbmV1"),
    Case("v2_retrain", "本脚本按第二版配置重训，用来核对训练路径跟正式训练一致"),
    # ---- 标签持有期：信号越慢、换手越低 ----
    Case("h3", "标签持有 3 根（12 小时）", horizon=3),
    Case("h6", "标签持有 6 根（1 天）", **H6),
    Case("h12", "标签持有 12 根（2 天）", horizon=12),
    # ---- 标签形态：排名 vs 原始收益 ----
    Case("h1_raw", "持有 1 根，原始收益标签（1% 截尾）", label_transform="raw_clip"),
    Case("h6_raw", "持有 1 天，原始收益标签", label_transform="raw_clip", **H6),
    # ---- 训练窗口 ----
    Case("h6_win180", "持有 1 天，滑动 180 天窗口", window_bars=6 * 180, **H6),
    Case("h6_win365", "持有 1 天，滑动 365 天窗口", window_bars=6 * 365, **H6),
    Case("h6_expanding", "持有 1 天，扩展窗口", window_bars=None, **H6),
    # ---- 损失 ----
    Case("h6_l2rank", "持有 1 天，排名标签上的 MSE 回归", objective="l2_rank", **H6),
    Case("h6_notail", "持有 1 天，不做首尾加权", tail_weight=1.0, **H6),
    Case("h6_neutral", "持有 1 天，标签剥离 Beta / Size", neutralize_label=True, **H6),
    # ---- 特征消融 ----
    Case("h6_noB", "持有 1 天，去掉 B 组（世坤因子）", drop_features=("alpha:",), **H6),
    Case("h6_noC", "持有 1 天，去掉 C 组（市场状态）", drop_features=("market:",), **H6),
    # ---- 流动性范围 ----
    Case("h6_p70", "持有 1 天，只用成交额截面前 30% 的币", min_percentile=0.7, **H6),
    # ---- 剥离暴露：去掉低波动 / Beta 倾向之后还剩多少 ----
    Case("v2_resid_vol", "正式模型打分，剥离 vol_42 暴露", source="official:LgbmV1", neutralize_scores=("vol42",)),
    Case("v2_resid_vol_beta", "正式模型打分，剥离 vol_42 + Beta 暴露", source="official:LgbmV1", neutralize_scores=("vol42", "beta")),
    # ---- 单因子基线：不用 ML，这个币池里单个原始特征能不能赚钱 ----
    *[Case(f"f_{name}", f"单因子 {name}（方向按选择段 IC 定）", source=f"factor:{name}") for name in FACTORS],
    # ---- 第三批：围绕 h6_raw（持有 1 天 + 原始收益标签）----
    Case("h6_raw_seed345", "h6_raw 换一组随机种子（3,4,5），看是不是运气", label_transform="raw_clip", seeds=(3, 4, 5), **H6),
    Case("h6_raw_p70", "h6_raw + 只用成交额前 30% 的币", label_transform="raw_clip", min_percentile=0.7, **H6),
    Case("h6_raw_p60", "h6_raw + 只用成交额前 40% 的币", label_transform="raw_clip", min_percentile=0.6, **H6),
    Case("h3_raw", "持有 12 小时 + 原始收益标签", label_transform="raw_clip", horizon=3),
    Case("h12_raw", "持有 2 天 + 原始收益标签", label_transform="raw_clip", horizon=12),
    Case("h6_raw_win180", "h6_raw + 滑动 180 天窗口", label_transform="raw_clip", window_bars=6 * 180, **H6),
    Case("h6_raw_expanding", "h6_raw + 扩展窗口", label_transform="raw_clip", window_bars=None, **H6),
    Case("h6_raw_l2", "h6_raw + MSE 回归（对截尾后的原始收益）", label_transform="raw_clip", objective="l2_rank", **H6),
    Case("h6_raw_notail", "h6_raw + 不做首尾加权", label_transform="raw_clip", tail_weight=1.0, **H6),
    Case("h6_raw_neutral", "h6_raw + 标签剥离 Beta / Size", label_transform="raw_clip", neutralize_label=True, **H6),
    Case("h6_raw_noB", "h6_raw + 去掉 B 组（世坤因子）", label_transform="raw_clip", drop_features=("alpha:",), **H6),
    Case("h6_raw_noC", "h6_raw + 去掉 C 组（市场状态）", label_transform="raw_clip", drop_features=("market:",), **H6),
    # ---- 第四批：多种子集成（单个模型树少、随机性大，两组种子的打分截面相关只有 0.43）----
    Case("h6_raw_ens6", "h6_raw 两组种子（0-2、3-5）共 6 个模型的打分平均", source="blend:h6_raw+h6_raw_seed345", **H6),
    Case("h6_raw_seed6789", "h6_raw 第三组种子（6,7,8,9）", label_transform="raw_clip", seeds=(6, 7, 8, 9), **H6),
    Case("h6_raw_seed1013", "h6_raw 第四组种子（10,11,12,13）", label_transform="raw_clip", seeds=(10, 11, 12, 13), **H6),
    Case("h6_raw_ens14", "h6_raw 四组种子共 14 个模型的打分平均",
         source="blend:h6_raw+h6_raw_seed345+h6_raw_seed6789+h6_raw_seed1013", **H6),
    # ---- 第五批：扩展窗口 + 原始收益标签（两段整体最均衡）的多种子集成 ----
    Case("h6_raw_exp_seed345", "h6_raw_expanding 换种子（3,4,5）", label_transform="raw_clip", window_bars=None, seeds=(3, 4, 5), **H6),
    Case("h6_raw_exp_seed678", "h6_raw_expanding 换种子（6,7,8）", label_transform="raw_clip", window_bars=None, seeds=(6, 7, 8), **H6),
    Case("h6_raw_exp_ens9", "h6_raw_expanding 三组种子共 9 个模型的打分平均",
         source="blend:h6_raw_expanding+h6_raw_exp_seed345+h6_raw_exp_seed678", **H6),
    # ---- 第六批（2026-10-09，研究起点 2023-01-01）：A 组加 OI / 多空比特征，其余同 LgbmV2 ----
    Case("d_base", "LgbmV2 配置（持有 1 天、原始收益、扩展窗口、9 种子），本批对照", **V2),
    Case("d_core", "d_base + 核心 6 个（OI 2 + 多空比 4）", extras=DERIVATIVES_CORE, **V2),
    Case("d_oi", "d_base + 只加 OI 2 个", extras=DERIVATIVES_OI, **V2),
    Case("d_ls", "d_base + 只加多空比 4 个", extras=DERIVATIVES_LS, **V2),
    Case("d_wide", "d_base + 全部 10 个候选（核心 + 边缘）",
         extras=DERIVATIVES_CORE + ("ls_top_position", "volume_to_oi_6", "oi_change_120", "ls_global_change_42"), **V2),
    # 换一组独立种子（9-17）复核 d_base vs d_core 的差别不是种子运气
    Case("d_base_s2", "d_base 换种子 9-17", **{**V2, "seeds": tuple(range(9, 18))}),
    Case("d_core_s2", "d_core 换种子 9-17", extras=DERIVATIVES_CORE, **{**V2, "seeds": tuple(range(9, 18))}),
    Case("d_ls_s2", "d_ls 换种子 9-17", extras=DERIVATIVES_LS, **{**V2, "seeds": tuple(range(9, 18))}),
    # 两组种子合并成 18 种子集成：单个 9 种子集成换种子后选择段中位数仍能差 0.4，最终比较用这一组
    Case("d_base_ens18", "d_base + d_base_s2 共 18 个模型的打分平均", source="blend:d_base+d_base_s2", **V2),
    Case("d_core_ens18", "d_core + d_core_s2 共 18 个模型的打分平均", source="blend:d_core+d_core_s2", **V2),
    Case("d_ls_ens18", "d_ls + d_ls_s2 共 18 个模型的打分平均", source="blend:d_ls+d_ls_s2", **V2),
    # ---- 第七批（2026-10-10）：V4 探索。新窗口——研究起点 2024-01-01（币池约为 2023 年的 1.6 倍）、最小训练 120 天
    # （第一份打分 2024-04-30）、验证段从 2025-03-01 起；去掉 B 组，只研究 A + C。训练配置同 LgbmV2 ----
    Case("w_v2", "新窗口下的 LgbmV2（A+B+C）", **W4),
    Case("w_v3", "新窗口下的 LgbmV3（A+B+C+多空比 4）", extras=DERIVATIVES_LS, **W4),
    Case("v4_ac", "V4 底座：A+C，无 B", with_b=False, **W4),
    Case("v4_ls", "A+C + 多空比 4", with_b=False, extras=DERIVATIVES_LS, **W4),
    Case("v4_pv", "A+C + 价量补充 4", with_b=False, extras=PRICE_VOLUME_EXTRAS, **W4),
    Case("v4_ls_oi", "A+C + 多空比 4 + OI 2", with_b=False, extras=DERIVATIVES_LS + DERIVATIVES_OI, **W4),
    Case("v4_ls_pv", "A+C + 多空比 4 + 价量补充 4", with_b=False, extras=DERIVATIVES_LS + PRICE_VOLUME_EXTRAS, **W4),
    Case("v4_all", "A+C + 多空比 4 + OI 2 + 价量补充 4", with_b=False,
         extras=DERIVATIVES_LS + DERIVATIVES_OI + PRICE_VOLUME_EXTRAS, **W4),
    # 结论：起点挪到 2024 后头 10 个月训练历史太短，同一时期（2024-05 ~ 2025-02）V2 配置毛 Sharpe 1.50 -> 0.21，
    # 选择段对特征决策没有区分度。V4 特征消融改回 2023 窗口（训练历史够），对照组是第六批的 d_base（V2）/ d_ls（V3）
    Case("v4h_ac", "2023 窗口：A+C，无 B", with_b=False, **V2),
    Case("v4h_ls", "2023 窗口：A+C + 多空比 4", with_b=False, extras=DERIVATIVES_LS, **V2),
    Case("v4h_pv", "2023 窗口：A+C + 价量补充 4", with_b=False, extras=PRICE_VOLUME_EXTRAS, **V2),
    Case("v4h_ls_pv", "2023 窗口：A+C + 多空比 4 + 价量补充 4", with_b=False, extras=DERIVATIVES_LS + PRICE_VOLUME_EXTRAS, **V2),
    Case("v4h_all", "2023 窗口：A+C + 多空比 4 + OI 2 + 价量补充 4", with_b=False,
         extras=DERIVATIVES_LS + DERIVATIVES_OI + PRICE_VOLUME_EXTRAS, **V2),
    # 入围的三个 + 底座换种子 9-17，再合成 18 种子集成
    *[Case(f"{name}_s2", f"{name} 换种子 9-17", with_b=False, extras=extras, **{**V2, "seeds": tuple(range(9, 18))})
      for name, extras in V4H_FINALISTS.items()],
    *[Case(f"{name}_ens18", f"{name} + {name}_s2 共 18 个模型的打分平均", source=f"blend:{name}+{name}_s2", **V2)
      for name in V4H_FINALISTS],
]
# ---- 第八批（2026-10-10）：探索 ↔ 正式流水线一致性核对（m_v4 跟正式 V4 逐格相同）。之后要进正式流水线的配置都先写成
# 模型类，再用 model_case 探索 ----
CASES += [
    model_case("m_v4", "跟 LgbmV4 完全相同的配置（model_case），本脚本训练", "LgbmV4"),
    Case("m_v4_official", "LgbmV4 正式模型的打分（MLAlpha.compute），应跟 m_v4 逐格相同", source="official:LgbmV4", horizon=6),
]


# ---------------------------------------------------------------------------
# 数据
# ---------------------------------------------------------------------------

def load_panel(refresh: bool):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"panel_{START_TIME}_{END_TIME}.pkl"
    if path.exists() and not refresh:
        return pickle.loads(path.read_bytes())
    print(f"正在从 ClickHouse 拉取 {START_TIME} ~ {END_TIME} 的 {INTERVAL} K 线……", flush=True)
    panel = load_universe_panel()
    path.write_bytes(pickle.dumps(panel, protocol=pickle.HIGHEST_PROTOCOL))
    return panel


def case_panel(panel, case: Case):
    """切掉 case 研究起点之前的数据：跟正式流水线从 research_start 取数一样，特征 / 流动性范围的 warm-up 都从这里开始。"""
    start = pd.Timestamp(case.research_start, tz="UTC")
    return panel if panel.index[0] >= start else panel.slice(panel.index >= start)


_FEATURE_CACHE: dict[tuple, tuple[pd.DataFrame, pd.DataFrame]] = {}


def scope_and_features(panel, case: Case) -> tuple[pd.DataFrame, pd.DataFrame]:
    key = (case.min_percentile, case.extras, case.with_b, panel.index[0])
    if key not in _FEATURE_CACHE:
        spec = case.spec
        scope = spec.liquidity.mask(panel)
        _FEATURE_CACHE[key] = (scope, build_features(panel, spec, scope))
    return _FEATURE_CACHE[key]


def _keep_columns(names: list[str], drop: tuple[str, ...]) -> list[int]:
    return [i for i, n in enumerate(names) if not any(n.startswith(p) for p in drop)]


# ---------------------------------------------------------------------------
# 训练 + 样本外打分
# ---------------------------------------------------------------------------

def train_case(panel, case: Case, case_dir: Path) -> pd.DataFrame:
    scope, features = scope_and_features(panel, case)
    frame = build_training_frame(
        panel, case.spec, horizon=case.horizon, delay=EXECUTION_DELAY_BARS, neutralize_label=case.neutralize_label,
        tail_quantile=case.tail_quantile, tail_weight=case.tail_weight, label_transform=case.label_transform,
        scope=scope, features=features,
    )
    cols = _keep_columns(frame.feature_names, case.drop_features)
    frame = dataclasses.replace(frame, features=frame.features[:, cols], feature_names=[frame.feature_names[i] for i in cols])

    # 打分用全部范围内的行（不只是标签已知的行：标签未知的行，比如快下架的币，实盘时照样要打分）
    times = pd.DatetimeIndex(features.index.get_level_values("start_time"))
    symbols = features.index.get_level_values("symbol")
    in_scope = scope.to_numpy()[panel.close.index.get_indexer(times), panel.close.columns.get_indexer(symbols)]
    matrix = features.to_numpy(dtype="float32")[:, cols]
    preds = np.full(len(features), np.nan)

    purge = case.horizon + EXECUTION_DELAY_BARS
    folds = plan_folds(
        research_start=pd.Timestamp(case.research_start, tz="UTC"), last_bar=panel.index[-1], interval=INTERVAL,
        retrain_every_bars=config.RETRAIN_EVERY_BARS, min_train_bars=case.min_train_bars, purge_bars=purge,
        train_window_bars=case.window_bars,
    )
    params = {**config.LGB_PARAMS, **dict(case.lgb_overrides)}
    fold_rows = []
    import lightgbm as lgb

    for fold in folds:
        rows = frame.rows_between(fold.train_from, fold.train_until)
        fit, valid = split_inner_validation(
            frame, rows, train_until=fold.train_until, valid_bars=case.valid_bars, purge_bars=purge, interval=INTERVAL
        )
        rel = fold.valid_from.strftime("%Y%m%dT%H%M")
        result = train_fold(
            frame, fit, valid, case_dir / "models" / rel, full=rows, objective=case.objective, seeds=case.seeds,
            lgb_params=params, num_boost_round=config.NUM_BOOST_ROUND, early_stopping_rounds=config.EARLY_STOPPING_ROUNDS,
            min_period_rows=config.MIN_PERIOD_ROWS, rel_prefix=rel,
        )
        lo, hi = times.searchsorted(fold.valid_from, "left"), times.searchsorted(fold.valid_until, "left")
        serve = np.zeros(len(features), dtype=bool)
        serve[lo:hi] = True
        serve &= in_scope
        if serve.any():
            boosters = [lgb.Booster(model_file=str(case_dir / "models" / f)) for f in result.files]
            preds[serve] = np.mean([b.predict(matrix[serve]) for b in boosters], axis=0)
        fold_rows.append({"valid_from": fold.valid_from, "n_window_rows": rows.stop - rows.start,
                          "best_iterations": "|".join(map(str, result.best_iterations)),
                          "inner_valid_ic_ir": float(np.mean(result.metrics["inner_valid_ic_ir_by_seed"]))})
    pd.DataFrame(fold_rows).to_csv(case_dir / "folds.csv", index=False)
    scores = pd.Series(preds, index=features.index).unstack("symbol")
    return scores.reindex(index=panel.close.index, columns=panel.close.columns)


def official_scores(panel, case: Case) -> pd.DataFrame:
    """`source="official:<模型类名>"`：直接用正式训练好的模型推断（`MLAlpha.compute`），模型文件在它的 model_dir。
    老写法 `source="official"` = LgbmV1。"""
    name = case.source.split(":", 1)[1] if ":" in case.source else "LgbmV1"
    return getattr(ml_models, name)().compute(panel)


def factor_scores(panel, case: Case) -> pd.DataFrame:
    """单因子：原始值套流动性范围，方向按**选择段**（研究起点 ~ validation_start）RankIC 的符号统一成"越大越好"。"""
    scope, _ = scope_and_features(panel, case)
    raw = FACTORS[case.source.split(":", 1)[1]](panel)
    raw = raw.where(np.isfinite(raw)).where(scope)
    label = forward_returns(panel.close, horizon=case.horizon, delay=EXECUTION_DELAY_BARS).where(scope)
    sel = panel.close.index < pd.Timestamp(case.validation_start, tz="UTC")
    a, b = raw[sel], label[sel]
    both = a.notna() & b.notna()
    ic = a.where(both).rank(axis=1).corrwith(b.where(both).rank(axis=1), axis=1).mean()
    print(f"  {case.name}：选择段 RankIC {ic:+.4f} → {'原方向' if ic >= 0 else '反向'}", flush=True)
    return raw if ic >= 0 else -raw


def blend_scores(case: Case) -> pd.DataFrame:
    """几个已跑完 case 的样本外打分取平均（任一缺失就是缺失）。

    取**原始预测值**的平均，跟 `MLAlpha.compute` 把多个种子的预测直接平均一致：两组 9 种子 blend 起来 = 同一批 18 个
    模型一起训练（训练集分箱的随机数是固定的，见 config.LGB_PARAMS["data_random_seed"]）。"""
    names = case.source.split(":", 1)[1].split("+")
    scores = [pd.read_pickle(OUT_DIR / n / "scores.pkl") for n in names]
    total = scores[0]
    for x in scores[1:]:
        total = total + x
    return total / len(scores)


def neutralize_scores(panel, scores: pd.DataFrame, names: tuple[str, ...]) -> pd.DataFrame:
    """逐期截面回归：打分 ~ 截距 + 所选暴露，取残差（sherpa.risk.neutralize）。"""
    from sherpa.backtest.style_exposure import default_style_exposures
    from sherpa.risk.neutralize import neutralize

    style = default_style_exposures(panel, benchmark_symbol=LgbmV1.spec.benchmark_symbol)
    available = {
        "vol42": panel.close.pct_change(fill_method=None).rolling(42).std(),
        "beta": style["beta"],
        "size": style["size"],
    }
    return neutralize(scores, {n: available[n] for n in names})


# ---------------------------------------------------------------------------
# 评估（多进程跑回测网格）。产出跟关卡3 同口径（同一套组合网格、成本、稳健性过滤、风格因子、季度统计），文件对应关系：
#   friction_grid.csv     <-> 关卡3 01_friction_summary.csv（每个组合 × 成本 × 段的绩效）
#   robustness.csv        <-> 04_robustness.csv
#   style_attribution.csv <-> 05_style_attribution.csv（BASE_COST 净收益对 6 个风格回归）
#   quarterly.csv         <-> 06_quarterly.csv
# 打分 → 截面排名 → 目标仓位 → 回测这条链跟关卡3 共用 sherpa.backtest.score_backtest；段从第一根有打分的 bar 起。
# ---------------------------------------------------------------------------

_W: dict[str, Any] = {}


def _init_worker(close, interval, ranked, segments, shift, ppy, style, active_start):
    _W.update(close=close, interval=interval, ranked=ranked, segments=segments, shift=shift, ppy=ppy, style=style,
              active_start=active_start)


def _run_combo(args: tuple[str, int]) -> tuple[list[dict], list[dict], dict]:
    weighting, rebalance = args
    key = {"weighting": weighting, "rebalance_every": rebalance}
    targets = target_path(_W["ranked"], evaluation.WEIGHTINGS[weighting], rebalance)
    gross, turnover = run_score_backtest(targets, _W["close"], _W["interval"], shift=_W["shift"], rebalance_every=rebalance)
    rows = [{**key, **r} for r in cost_segment_rows(gross, turnover, evaluation.COST_MODELS, _W["segments"],
                                                    periods_per_year=_W["ppy"])]
    net = gross - turnover.map(evaluation.COST_MODELS[evaluation.BASE_COST].cost)
    net = net[net.index >= _W["active_start"]]
    attribution = [
        {**key, "segment": name,
         **attribute(net[mask.reindex(net.index, fill_value=False)], _W["style"], periods_per_year=_W["ppy"])}
        for name, mask in _W["segments"].items()
    ]
    stats = period_stats(net, periods_per_year=_W["ppy"])
    full = stats["return"].dropna()  # 不足 60 根 bar 的零头季度不计（同关卡3）
    quarterly = {**key, "quarters": len(full),
                 "positive_quarter_frac": float((full > 0).mean()) if len(full) else float("nan"),
                 **{f"sharpe[{q}]": v for q, v in stats["sharpe"].items()},
                 **{f"return[{q}]": v for q, v in stats["return"].items()}}
    return rows, attribution, quarterly


def robustness(grid: pd.DataFrame) -> pd.DataFrame:
    """同关卡3 `_robustness`：每个成本一行，全部组合两段净 Sharpe 的中位数 / 为正占比 / 两段都为正的占比；
    选择段（零成本下）空仓比例超过 ROBUSTNESS_MAX_FLAT 的组合不计入。"""
    keys = ["weighting", "rebalance_every"]
    sel_zero = grid[(grid.segment == "selection_oos") & (grid.cost_model == "zero")].set_index(keys)["flat_bar_fraction"]
    usable = sel_zero[sel_zero <= evaluation.ROBUSTNESS_MAX_FLAT].index
    rows = []
    for cost, g in grid.groupby("cost_model", sort=False):
        wide = g.set_index(keys).pivot(columns="segment", values="net_sharpe")
        wide = wide.loc[wide.index.intersection(usable)]
        sel, val = wide["selection_oos"], wide["validation"]
        rows.append({"cost_model": cost, "n_combos": len(wide),
                     "selection_median": sel.median(), "validation_median": val.median(),
                     "selection_positive_frac": (sel > 0).mean(), "validation_positive_frac": (val > 0).mean(),
                     "both_positive_frac": ((sel > 0) & (val > 0)).mean()})
    return pd.DataFrame(rows)


def evaluate_case(panel, case: Case, scores: pd.DataFrame, case_dir: Path, workers: int) -> None:
    scope, features = scope_and_features(panel, case)
    close = panel.close
    # 跟关卡3 一样：打分先套流动性范围（= 研究线评估掩码，训练脚本校验过两者一致），再逐期截面排名
    ranked = evaluation.cross_sectional_rank(scores.reindex(index=close.index, columns=close.columns).where(scope))
    active_start = ranked.notna().any(axis=1).idxmax()
    validation_start = pd.Timestamp(case.validation_start, tz="UTC")
    segments = {
        "selection_oos": pd.Series((close.index >= active_start) & (close.index < validation_start), index=close.index),
        "validation": pd.Series(close.index >= validation_start, index=close.index),
    }

    label_1 = forward_returns(close, horizon=1, delay=EXECUTION_DELAY_BARS).where(scope)
    label_h = forward_returns(close, horizon=case.horizon, delay=EXECUTION_DELAY_BARS).where(scope)
    vol = close.pct_change(fill_method=None).rolling(42).std()
    pd.DataFrame(evaluation.diagnostics(ranked, label_1, label_h, vol, segments)).to_csv(case_dir / "diagnostics.csv", index=False)

    shift = 1 + EXECUTION_DELAY_BARS
    ppy = pd.Timedelta(days=365) / interval_to_timedelta(INTERVAL)
    style = style_factor_returns(close, panel.quote_volume, scope, interval=INTERVAL, shift=shift,
                                 benchmark_symbol=LgbmV1.spec.benchmark_symbol)
    combos = [(w, r) for w in evaluation.WEIGHTINGS for r in evaluation.REBALANCE_EVERY]
    with ProcessPoolExecutor(max_workers=workers, initializer=_init_worker,
                             initargs=(close, INTERVAL, ranked, segments, shift, ppy, style, active_start)) as pool:
        results = list(pool.map(_run_combo, combos))
    grid = pd.DataFrame([row for rows, _, _ in results for row in rows])
    grid.to_csv(case_dir / "friction_grid.csv", index=False)
    robustness(grid).to_csv(case_dir / "robustness.csv", index=False)
    pd.DataFrame([row for _, rows, _ in results for row in rows]).to_csv(case_dir / "style_attribution.csv", index=False)
    pd.DataFrame([q for _, _, q in results]).to_csv(case_dir / "quarterly.csv", index=False)


# ---------------------------------------------------------------------------
# 汇总：每个 case 一行，列跟关卡3 的 04 / 05 / 06 对应（全部组合的中位数，不挑最高格）
# ---------------------------------------------------------------------------

def summarize(cases: list[Case]) -> pd.DataFrame:
    rows = []
    for case in cases:
        d = OUT_DIR / case.name
        if not (d / "robustness.csv").exists():  # 没跑过评估（或产出已删）的 case 不进汇总
            continue
        rob = pd.read_csv(d / "robustness.csv").set_index("cost_model")
        att = pd.read_csv(d / "style_attribution.csv").groupby("segment")[["alpha_sharpe", "beta[low_vol]"]].median()
        qtr = pd.read_csv(d / "quarterly.csv")
        grid = pd.read_csv(d / "friction_grid.csv")
        val = grid[(grid.segment == "validation") & (grid.cost_model == "zero")]
        diag = pd.read_csv(d / "diagnostics.csv").set_index("segment")
        rows.append({
            "case": case.name, "note": case.note,
            "taker_sel": rob.loc["all_taker", "selection_median"], "taker_val": rob.loc["all_taker", "validation_median"],
            "taker_both_pos": rob.loc["all_taker", "both_positive_frac"],
            "maker_sel": rob.loc["all_maker", "selection_median"], "maker_val": rob.loc["all_maker", "validation_median"],
            "gross_sel": rob.loc["zero", "selection_median"], "gross_val": rob.loc["zero", "validation_median"],
            "alpha_sel": att.loc["selection_oos", "alpha_sharpe"], "alpha_val": att.loc["validation", "alpha_sharpe"],
            "lowvol_beta_val": att.loc["validation", "beta[low_vol]"],
            "pos_quarter_med": qtr.positive_quarter_frac.median(),
            "pos_quarter_ge60": (qtr.positive_quarter_frac >= 0.6).mean(),
            "val_turnover_med": val.turnover_per_bar.median(), "val_breakeven_bps_med": val.breakeven_cost_bps.median(),
            "n_combos": int(rob.loc["all_taker", "n_combos"]),
            "val_rank_ic_h": diag.loc["validation", "rank_ic_h"], "val_vol42_exposure": diag.loc["validation", "vol42_exposure"],
        })
    out = pd.DataFrame(rows)
    out.to_csv(OUT_DIR / "summary.csv", index=False)
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ML alpha 探索实验")
    parser.add_argument("--cases", default="", help="逗号分隔的 case 名，空 = 全部")
    parser.add_argument("--refresh-panel", action="store_true", help="重新从 ClickHouse 取数（默认用缓存）")
    parser.add_argument("--summary-only", action="store_true")
    parser.add_argument("--skip-existing", action="store_true", help="已有 friction_grid.csv 的 case 跳过")
    parser.add_argument("--reeval", action="store_true", help="已有 scores.pkl 的 case 只重新评估（评估网格改了时用），不重训")
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args(argv)

    wanted = [c for c in CASES if not args.cases or c.name in args.cases.split(",")]
    if not args.summary_only:
        full_panel = load_panel(args.refresh_panel)
        print(f"panel：{len(full_panel.symbols)} 个 symbol × {len(full_panel.index)} 根 bar", flush=True)
        for case in wanted:
            case_dir = OUT_DIR / case.name
            if args.skip_existing and (case_dir / "friction_grid.csv").exists():
                print(f"[跳过] {case.name}", flush=True)
                continue
            case_dir.mkdir(parents=True, exist_ok=True)
            panel = case_panel(full_panel, case)
            started = time.monotonic()
            if args.reeval and (case_dir / "scores.pkl").exists():
                evaluate_case(panel, case, pd.read_pickle(case_dir / "scores.pkl"), case_dir, args.workers)
                print(f"[完成] {case.name}：只重新评估 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)
                continue
            if case.source.startswith("official"):
                scores = official_scores(panel, case)
            elif case.source.startswith("factor:"):
                scores = factor_scores(panel, case)
            elif case.source.startswith("blend:"):
                scores = blend_scores(case)
            else:
                scores = train_case(panel, case, case_dir)
            if case.neutralize_scores:
                scores = neutralize_scores(panel, scores, case.neutralize_scores)
            scores.to_pickle(case_dir / "scores.pkl")
            trained = time.monotonic() - started
            evaluate_case(panel, case, scores, case_dir, args.workers)
            print(f"[完成] {case.name}：训练 / 打分 {trained / 60:.1f} 分钟，评估 {(time.monotonic() - started - trained) / 60:.1f} 分钟", flush=True)
    summary = summarize(CASES)
    pd.set_option("display.width", 250)
    print(summary.drop(columns=["note"]).round(3).to_string(index=False))


if __name__ == "__main__":
    main()
