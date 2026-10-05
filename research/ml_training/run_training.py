"""ML alpha 的滚动训练（研究线的步骤 0）：按固定节奏在每个重训时点训练一个模型，冻结成文件，写进模型清单。

    CH_HOST=... CH_PASSWORD=... python research/ml_training/run_training.py --track MLalpha

研究线 `track.json` 的 `alphas.modules` 里每个 `MLAlpha` 子类都会被训练（模型文件在它的 `model_dir`）。设计见
`sherpa/alpha/custom/ML_ALPHA_DESIGN.md` §4、§7。流程：

1. 取 `research_start ~ research_end` 的全市场面板（`--until holdout` 覆盖到 holdout，研究结论定下来之前不要用）；
2. 一次算好整段的特征、标签、损失掩码（模型的 `spec.liquidity`，必须跟研究线 `track.json` 的 `tradable_mask` 一致，
   开头校验），只保留掩码内、标签已知的行；
3. 按时间表（`dataset.plan_folds`）逐个重训时点训练：训练窗口是 τ 之前滑动的 `TRAIN_WINDOW_BARS` 根 bar，训练行
   只取 `t <= τ − (horizon + delay)`；每个随机种子两步——① 窗口里最近 `INNER_VALID_BARS` 根做内部验证段、早停得到
   最佳轮数，② 用整个窗口按最佳轮数重训，保存第②步的模型；
4. **增量**：清单里已有、文件齐全的重训时点直接跳过。特征清单或训练配置变了会拒绝续训，要 `--force` 全部重训；
5. 用清单里全部模型对各自服务的时间段做样本外预测，逐期算 RankIC，写 `<研究线>/results/ml_training/`：
   - `folds.csv`：每个重训时点一行（训练行数、早停轮数、内部验证 IC_IR、服务期内的样本外 RankIC）；
   - `oos_summary.csv`：拼起来的样本外 RankIC 按选择段 / 验证段汇总。

样本外 RankIC 只在损失掩码内算，跟研究流水线阶段一的 IC 同一个口径（标签同样套了掩码）。注意 B 组特征（世坤
因子名单）是在选择段上挑出来的，选择段的样本外数字偏乐观，看验证段。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

from sherpa.alpha import registry
from sherpa.alpha.custom.ml.alpha import MLAlpha, load_booster
from sherpa.alpha.custom.ml.manifest import Manifest, ModelEntry, fold_dir_name, format_ts, load_manifest, save_manifest

import config
from data import (
    BENCHMARK_SYMBOL,
    END_TIME,
    EXECUTION_DELAY_BARS,
    HOLDOUT_END,
    HORIZON_BARS,
    INTERVAL,
    START_TIME,
    VALIDATION_START,
    load_universe_panel,
)
from dataset import TrainingFrame, build_training_frame, liquidity_from_tradable, plan_folds, split_inner_validation
from trainer import ic_stats, spearman_by_period, train_fold

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "_shared"))
from track import Track, load_track  # noqa: E402

STAGE = "ml_training"


def _config_payload() -> dict:
    # 损失掩码不在这里：它是模型 spec.liquidity 的一部分，已经进了特征指纹。
    return {
        **config.as_dict(),
        "interval": INTERVAL,
        "research_start": START_TIME,
        "horizon_bars": HORIZON_BARS,
        "execution_delay_bars": EXECUTION_DELAY_BARS,
        "benchmark_symbol": BENCHMARK_SYMBOL,
    }


def _check_liquidity(track: Track, alpha: MLAlpha) -> None:
    """模型训练 / 推断用的流动性范围（spec.liquidity）必须跟研究流水线评估用的外层掩码（track.json）一致。"""
    evaluation = liquidity_from_tradable(track.tradable)
    if evaluation != alpha.spec.liquidity:
        raise SystemExit(
            f"{alpha.qualified_name} 的流动性范围跟研究线 {track.id} 的评估掩码不一致：\n"
            f"  模型 spec.liquidity             = {alpha.spec.liquidity}\n"
            f"  track.json 的 tradable_mask 换算 = {evaluation}\n"
            "两边改成一样再训练（模型在 sherpa/alpha/custom/ml/models.py，研究线在 track.json 的 preprocess.tradable_mask）"
        )


def _fingerprint(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _ml_alphas(track: Track) -> list[type[MLAlpha]]:
    classes = [registry.get(name) for name in track.select_alphas()]
    ml = [cls for cls in classes if issubclass(cls, MLAlpha)]
    if not ml:
        raise SystemExit(f"研究线 {track.id} 里没有 MLAlpha 子类，没有模型要训练")
    return ml


def _prepare_manifest(alpha: MLAlpha, payload: dict, force: bool) -> Manifest:
    fingerprint = _fingerprint(payload)
    existing = load_manifest(alpha.model_dir)
    fresh = Manifest(
        model=alpha.model_name,
        feature_fingerprint=alpha.spec.fingerprint,
        feature_names=list(alpha.spec.feature_names),
        config_fingerprint=fingerprint,
        config=payload,
    )
    if existing is None:
        return fresh
    same = existing.feature_fingerprint == alpha.spec.fingerprint and existing.config_fingerprint == fingerprint
    if same:
        return existing
    if not force:
        raise SystemExit(
            f"{alpha.model_dir} 里已有模型的特征清单或训练配置跟现在不一致"
            f"（特征 {existing.feature_fingerprint} vs {alpha.spec.fingerprint}，配置 {existing.config_fingerprint} vs {fingerprint}）。"
            "确认要全部重训就加 --force（会删掉旧模型文件），或者给新配置开一个新的模型名"
        )
    print(f"  --force：删掉 {alpha.model_dir} 下的旧模型，全部重训")
    shutil.rmtree(alpha.model_dir)
    return fresh


def _entry_complete(alpha: MLAlpha, entry: ModelEntry) -> bool:
    return all((alpha.model_dir / rel).exists() for rel in entry.files)


def train_alpha(alpha: MLAlpha, frame: TrainingFrame, panel_last_bar: pd.Timestamp, payload: dict, force: bool) -> Manifest:
    manifest = _prepare_manifest(alpha, payload, force)
    done = {e.valid_from: e for e in manifest.entries if _entry_complete(alpha, e)}
    manifest.entries = list(done.values())
    purge = HORIZON_BARS + EXECUTION_DELAY_BARS
    folds = plan_folds(
        research_start=pd.Timestamp(START_TIME, tz="UTC"),
        last_bar=panel_last_bar,
        interval=INTERVAL,
        retrain_every_bars=config.RETRAIN_EVERY_BARS,
        min_train_bars=config.MIN_TRAIN_BARS,
        purge_bars=purge,
        train_window_bars=config.TRAIN_WINDOW_BARS,
    )
    todo = [f for f in folds if format_ts(f.valid_from) not in done]
    print(f"  时间表 {len(folds)} 个重训时点（{format_ts(folds[0].valid_from)} 起，每 {config.RETRAIN_EVERY_BARS} 根 bar），"
          f"已有 {len(folds) - len(todo)} 个，本次训练 {len(todo)} 个 × {len(config.SEEDS)} 个种子")

    started = time.monotonic()
    for i, fold in enumerate(todo, 1):
        rows = frame.rows_between(fold.train_from, fold.train_until) # 切出这个fold的训练段数据
        if rows.stop <= rows.start:
            raise SystemExit(f"{format_ts(fold.valid_from)} 之前没有可训练的行（损失掩码 / 标签全空？）")
        if frame.times[rows.stop - 1] > fold.train_until:  # purge 自检：训练行的标签必须在 τ 之前已经实现
            raise AssertionError(f"训练行越过了 {fold.train_until}")
        # ① 早停用：拟合段 + 最近 INNER_VALID_BARS 根的内部验证段；② 重训用：整个训练窗口 rows（见 trainer.train_fold）
        fit, valid = split_inner_validation(
            frame, rows, train_until=fold.train_until, valid_bars=config.INNER_VALID_BARS, purge_bars=purge, interval=INTERVAL
        )
        rel = fold_dir_name(fold.valid_from)
        result = train_fold(
            frame, fit, valid, alpha.model_dir / rel,
            full=rows,
            objective=config.OBJECTIVE,
            seeds=config.SEEDS,
            lgb_params=config.LGB_PARAMS,
            num_boost_round=config.NUM_BOOST_ROUND,
            early_stopping_rounds=config.EARLY_STOPPING_ROUNDS,
            min_period_rows=config.MIN_PERIOD_ROWS,
            rel_prefix=rel,
        )
        manifest.entries.append(ModelEntry(
            valid_from=format_ts(fold.valid_from),
            valid_until=format_ts(fold.valid_until),
            train_rows_until=format_ts(fold.train_until),
            files=result.files,
            n_train_rows=rows.stop - rows.start,  # 最终模型（重训）用的行数 = 整个训练窗口
            n_inner_valid_rows=valid.stop - valid.start,
            best_iterations=result.best_iterations,
            metrics=result.metrics,
        ))
        save_manifest(alpha.model_dir, manifest)  # 每训完一个就落盘，中途打断下次从这里续
        scores = ", ".join(f"{s:.3f}" for s in result.metrics["inner_valid_ic_ir_by_seed"])
        print(f"  [{i}/{len(todo)}] {format_ts(fold.valid_from)} 拟合 {fit.stop - fit.start:,} 行 / 验证 {valid.stop - valid.start:,} 行"
              f" → 早停轮数 {result.best_iterations}，内部验证 IC_IR [{scores}] → 整窗重训 {rows.stop - rows.start:,} 行，"
              f"已用时 {(time.monotonic() - started) / 60:.1f} 分钟", flush=True)
    return manifest


def evaluate(alpha: MLAlpha, manifest: Manifest, frame: TrainingFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """清单里每个模型只预测它服务的那段时间（样本外），逐期 RankIC。"""
    entries = manifest.sorted_entries()
    assigned = manifest.assign(frame.times)
    pred = np.full(len(frame), np.nan)
    fold_rows = []
    for i, entry in enumerate(entries):
        rows = assigned == i
        row = {"valid_from": entry.valid_from, "valid_until": entry.valid_until, "n_train_rows": entry.n_train_rows,
               "best_iterations": "|".join(map(str, entry.best_iterations)),
               "inner_valid_ic_ir": float(np.mean(entry.metrics.get("inner_valid_ic_ir_by_seed", [np.nan])))}
        if rows.any():
            pred[rows] = np.mean([load_booster(alpha.model_dir / f).predict(frame.features[rows]) for f in entry.files], axis=0)
            try:
                row.update(ic_stats(spearman_by_period(pred[rows], frame.label[rows], frame.times[rows],
                                                       min_period_rows=config.MIN_PERIOD_ROWS)))
            except ValueError:
                pass
        fold_rows.append(row)

    covered = np.isfinite(pred)
    ic = spearman_by_period(pred[covered], frame.label[covered], frame.times[covered], min_period_rows=config.MIN_PERIOD_ROWS)
    validation_start = pd.Timestamp(VALIDATION_START, tz="UTC")
    summary = [
        {"segment": "selection(样本外，特征名单在此段选出，偏乐观)", **ic_stats(ic[ic.index < validation_start])},
        {"segment": "validation(样本外)", **ic_stats(ic[ic.index >= validation_start])},
        {"segment": "all", **ic_stats(ic)},
    ]
    return pd.DataFrame(fold_rows), pd.DataFrame(summary)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="ML alpha 滚动训练")
    parser.add_argument("--track", required=True, help="研究线 id（research/alpha_research/<id>/）或目录")
    parser.add_argument("--until", choices=("research", "holdout"), default="research",
                        help="数据取到 research_end（默认）还是 holdout_end")
    parser.add_argument("--force", action="store_true", help="特征清单或训练配置变了时，删掉旧模型全部重训")
    parser.add_argument("--check-only", action="store_true",
                        help="只校验模型的流动性范围跟研究线评估掩码一致，不取数、不训练（编排脚本每次都先跑这一下）")
    args = parser.parse_args(argv)

    track = load_track(args.track)
    alphas = [cls() for cls in _ml_alphas(track)]
    payload = _config_payload()
    for alpha in alphas:
        _check_liquidity(track, alpha)  # 先校验再取数，配错了不白等
    if args.check_only:
        print(f"[校验通过] 研究线 {track.id}：{[a.qualified_name for a in alphas]} 的流动性范围 = 评估掩码 {track.tradable}")
        return
    print(f"研究线 {track.id}：训练 {[a.qualified_name for a in alphas]}")
    print(f"  目标 {config.OBJECTIVE}；首尾加权 {config.TAIL_QUANTILE:.0%} × {config.TAIL_WEIGHT}；标签中性化 {config.NEUTRALIZE_LABEL}")

    end_time = END_TIME if args.until == "research" else HOLDOUT_END
    print(f"\n正在从 ClickHouse 拉取 {START_TIME} ~ {end_time} 的 {INTERVAL} K 线……")
    panel = load_universe_panel(end_time=end_time)
    print(f"universe={len(panel.symbols)} 个 symbol，共 {len(panel.index)} 根 bar")

    results_dir = track.stage_results_dir(STAGE)
    results_dir.mkdir(parents=True, exist_ok=True)
    for alpha in alphas:
        print(f"\n== {alpha.qualified_name}：{len(alpha.spec.feature_names)} 个特征，模型目录 {alpha.model_dir} ==")
        print(f"  流动性范围（特征排名 + 损失掩码 + 推断，跟研究线评估掩码已校验一致）：{alpha.spec.liquidity}")
        started = time.monotonic()
        frame = build_training_frame(
            panel, alpha.spec,
            horizon=HORIZON_BARS, delay=EXECUTION_DELAY_BARS, neutralize_label=config.NEUTRALIZE_LABEL,
            tail_quantile=config.TAIL_QUANTILE, tail_weight=config.TAIL_WEIGHT,
        )
        print(f"  训练集（损失掩码内、标签已知）{len(frame):,} 行，构建用时 {time.monotonic() - started:.0f} 秒")
        manifest = train_alpha(alpha, frame, panel.index[-1], payload, args.force)

        folds, summary = evaluate(alpha, manifest, frame)
        prefix = alpha.model_name
        folds.to_csv(results_dir / f"{prefix}_folds.csv", index=False)
        summary.to_csv(results_dir / f"{prefix}_oos_summary.csv", index=False)
        print("\n  样本外 RankIC（每个模型只预测它服务的那段时间，损失掩码内）：")
        print(summary.round(4).to_string(index=False))
        print(f"  结果：{results_dir / f'{prefix}_folds.csv'}、{results_dir / f'{prefix}_oos_summary.csv'}")


if __name__ == "__main__":
    main()
