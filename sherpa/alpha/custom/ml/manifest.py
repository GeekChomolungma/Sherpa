"""模型清单（manifest）：滚动训练产出的每个模型负责哪一段时间、用什么特征训练的。纯 JSON，不依赖任何 ML 库。

滚动训练（`research/ml_training/`）每个重训时点 τ 训练一个模型，它只服务 `[valid_from, valid_until)` 这段时间：
`valid_from = τ`，`valid_until` = 下一个重训时点。训练数据只用 τ 之前、标签已经完全实现的行，所以**每一行的打分
都来自训练截止早于它的模型**（point-in-time）。清单覆盖不到的行没有模型，打分为 NaN。

目录结构（`<模型根目录>/<模型名>/`）：

    manifest.json
    20220702T0000/seed0.txt, seed1.txt, ...   每个重训时点一个子目录，存各随机种子训练出的模型文件

模型文件不进 git，manifest.json 可以进（体积小，方便复现和审计）。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

MANIFEST_FILE = "manifest.json"
SCHEMA_VERSION = 1


def _ts(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


def format_ts(ts: pd.Timestamp) -> str:
    return _ts(str(ts)).strftime("%Y-%m-%dT%H:%M:%SZ")


def fold_dir_name(valid_from: pd.Timestamp) -> str:
    return _ts(str(valid_from)).strftime("%Y%m%dT%H%M")


@dataclass
class ModelEntry:
    """一个重训时点的模型（多个随机种子，推断时取平均）。"""

    valid_from: str
    valid_until: str
    train_rows_until: str
    files: list[str]
    n_train_rows: int = 0
    n_inner_valid_rows: int = 0
    best_iterations: list[int] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    @property
    def valid_from_ts(self) -> pd.Timestamp:
        return _ts(self.valid_from)

    @property
    def valid_until_ts(self) -> pd.Timestamp:
        return _ts(self.valid_until)


@dataclass
class Manifest:
    model: str
    feature_fingerprint: str
    feature_names: list[str]
    config_fingerprint: str
    config: dict[str, Any] = field(default_factory=dict)
    entries: list[ModelEntry] = field(default_factory=list)

    def sorted_entries(self) -> list[ModelEntry]:
        return sorted(self.entries, key=lambda e: e.valid_from_ts)

    def assign(self, times: pd.DatetimeIndex | np.ndarray) -> np.ndarray:
        """每个时间点该用第几个模型（下标对应 `sorted_entries()`），没有模型覆盖的为 -1。"""
        entries = self.sorted_entries()
        times = pd.DatetimeIndex(times)
        out = np.full(len(times), -1, dtype=np.int64)
        if not entries:
            return out
        starts = pd.DatetimeIndex([e.valid_from_ts for e in entries])
        ends = pd.DatetimeIndex([e.valid_until_ts for e in entries])
        pos = starts.searchsorted(times, side="right") - 1
        inside = pos >= 0
        inside[inside] = times[inside] < ends[pos[inside]]
        out[inside] = pos[inside]
        return out

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "model": self.model,
            "feature_fingerprint": self.feature_fingerprint,
            "feature_names": self.feature_names,
            "config_fingerprint": self.config_fingerprint,
            "config": self.config,
            "entries": [asdict(e) for e in self.sorted_entries()],
        }

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> "Manifest":
        if raw.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(f"模型清单 schema_version={raw.get('schema_version')!r}，当前代码只认 {SCHEMA_VERSION}")
        return cls(
            model=raw["model"],
            feature_fingerprint=raw["feature_fingerprint"],
            feature_names=list(raw["feature_names"]),
            config_fingerprint=raw["config_fingerprint"],
            config=dict(raw.get("config", {})),
            entries=[ModelEntry(**e) for e in raw.get("entries", [])],
        )


def manifest_path(model_dir: Path) -> Path:
    return Path(model_dir) / MANIFEST_FILE


def load_manifest(model_dir: Path) -> Optional[Manifest]:
    path = manifest_path(model_dir)
    if not path.exists():
        return None
    return Manifest.from_json(json.loads(path.read_text(encoding="utf-8")))


def save_manifest(model_dir: Path, manifest: Manifest) -> Path:
    path = manifest_path(model_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest.to_json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)  # 先写临时文件再替换：训练中途被打断也不会留下半截清单
    return path
