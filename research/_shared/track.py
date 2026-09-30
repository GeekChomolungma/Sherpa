"""研究线（track）配置：一条 alpha 研究线"研究哪些因子、用什么处理链、看哪些 regime、走哪几关"。

family（worldquant / custom …）回答"因子从哪来"，是 sherpa 层的概念；track 回答"这一轮研究怎么做"，
是 research 层的概念，两者正交——一条 track 可以同时收 worldquant 和 custom 的因子。

每条研究线是 `research/alpha_research/<track_id>/` 一个目录：一份 `track.json`（字段见
`research/alpha_research/README.md`）+ 这条线自己的编排脚本 `run_track.sh`。整条流水线的产出都归档在
研究线目录下：`results/<阶段>/`（各阶段的明细产出）和 `handoff/<阶段>.json`（阶段之间的交接文件，见
`handoff.py`）。各关卡目录只放代码，不再放某条研究线的结果，不同研究线互不覆盖。

跟 `research_config.json` 的分工：时间窗（window）、IC 标签口径（label）、大盘锚点（market）、成本
（costs）是**全局**的，track 不能覆盖——不同研究线的结论要能横向比较，这几项必须一致。

放在 `research/_shared/`：阶段一（`alpha_research/_pipeline/`）和各关卡都要读研究线配置。各脚本把这个目录
插进 `sys.path` 后 `from track import load_track`。

也可以当命令行工具用，给编排脚本读字段：
    python track.py <track_id 或目录> <字段>
字段：id / dir / profile_path / results_dir / handoff_dir / neutralize / matrix_top_k / min_abs_t /
      mode.orthogonalization / mode.synthesis
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Union

from sherpa.alpha import registry
from sherpa.metrics.regime import REGIME_DIMENSIONS

ALPHA_RESEARCH_DIR = Path(__file__).resolve().parents[1] / "alpha_research"
TRACK_FILE = "track.json"

# 可以按研究线选择"真跑"还是"透传"的关卡。关卡3（摩擦）所有研究线都必须真跑，不在这里。
GATE_MODES = ("run", "passthrough")
OPTIONAL_GATES = ("orthogonalization", "synthesis")

# 关卡2 透传时，把候选集直接变成哪些配方（`factor_synthesis/passthrough.py`）。
DEFAULT_SYNTHESIS_PASSTHROUGH: dict[str, Any] = {"singles": True, "equal_weight": True, "routed": True}


@dataclass(frozen=True)
class Track:
    id: str
    dir: Path
    description: str
    alpha_modules: tuple[str, ...]
    alpha_family: Optional[str]
    tradable: Union[bool, Mapping[str, Any]]
    neutralize: bool
    regime_dimensions: tuple[str, ...]
    matrix_top_k: int
    min_abs_t: float
    gate_modes: Mapping[str, str] = field(default_factory=dict)
    synthesis_passthrough: Mapping[str, Any] = field(default_factory=dict)

    @property
    def _variant(self) -> str:
        # 关掉中性化的对照版本整条流水线换一套目录，两版不会互相覆盖。
        return "" if self.neutralize else "_without_neutralization"

    @property
    def profile_path(self) -> Path:
        """阶段一长表。"""
        return self.dir / f"regime_alpha_profile{self._variant}.csv"

    @property
    def results_dir(self) -> Path:
        return self.dir / f"results{self._variant}"

    @property
    def handoff_dir(self) -> Path:
        return self.dir / f"handoff{self._variant}"

    def stage_results_dir(self, stage: str) -> Path:
        """某个阶段（report / orthogonalization / synthesis / friction）的明细产出目录。"""
        return self.results_dir / stage

    def handoff_path(self, stage: str) -> Path:
        """某个阶段产出的交接文件。"""
        return self.handoff_dir / f"{stage}.json"

    def gate_mode(self, gate: str) -> str:
        return self.gate_modes.get(gate, "run")

    def import_alpha_modules(self) -> None:
        """import 一遍 `alphas.modules`，触发里面因子的 `@register_alpha`。多进程 worker 启动时也要调。"""
        for module in self.alpha_modules:
            importlib.import_module(module)

    def select_alphas(self) -> list[str]:
        """这条研究线的因子：定义在 `alphas.modules`（含子模块）里、且 family 匹配的已注册因子。

        按 `cls.__module__` 判断归属，所以同一个 family 下不同主题的模块（custom.starter / custom.xxx）
        能分成不同的研究线。返回 registry 的 qualified_name，顺序同注册顺序。
        """
        self.import_alpha_modules()
        selected = [
            name
            for name, cls in registry.all(family=self.alpha_family).items()
            if any(cls.__module__ == m or cls.__module__.startswith(m + ".") for m in self.alpha_modules)
        ]
        if not selected:
            raise SystemExit(
                f"track {self.id!r}：alphas.modules={list(self.alpha_modules)} / family={self.alpha_family!r} "
                "下一个已注册的因子都没有，检查模块路径和 @register_alpha"
            )
        return selected


def resolve_track_dir(name_or_path: Union[str, Path]) -> Path:
    """`worldquant_101` 这种短名解析成 `research/alpha_research/worldquant_101/`；也接受目录路径。"""
    candidate = Path(name_or_path)
    if not (candidate / TRACK_FILE).exists():
        candidate = ALPHA_RESEARCH_DIR / str(name_or_path)
    if not (candidate / TRACK_FILE).exists():
        raise SystemExit(f"找不到研究线 {name_or_path!r}：{candidate / TRACK_FILE} 不存在")
    return candidate.resolve()


def load_track(name_or_path: Union[str, Path]) -> Track:
    track_dir = resolve_track_dir(name_or_path)
    raw = json.loads((track_dir / TRACK_FILE).read_text(encoding="utf-8"))

    track_id = raw["id"]
    if track_id != track_dir.name:
        raise SystemExit(f"{track_dir / TRACK_FILE} 的 id={track_id!r} 跟目录名 {track_dir.name!r} 不一致")

    alphas = raw["alphas"]
    modules = alphas["modules"]
    if isinstance(modules, str) or not modules:
        raise SystemExit(f"track {track_id!r}：alphas.modules 必须是非空的模块路径列表")

    preprocess = raw.get("preprocess", {})
    tradable = preprocess.get("tradable_mask", True)
    if not isinstance(tradable, (bool, dict)):
        raise SystemExit(f"track {track_id!r}：preprocess.tradable_mask 只能是 true / false / 门槛参数对象")

    dimensions = tuple(raw.get("regime", {}).get("dimensions", REGIME_DIMENSIONS))
    unknown = [d for d in dimensions if d not in REGIME_DIMENSIONS]
    if unknown or not dimensions:
        raise SystemExit(f"track {track_id!r}：regime.dimensions={list(dimensions)} 不合法，可选 {list(REGIME_DIMENSIONS)}")

    stages = raw.get("stages", {})
    unknown_stages = [s for s in stages if s not in OPTIONAL_GATES]
    if unknown_stages:
        raise SystemExit(
            f"track {track_id!r}：stages 只能配置 {list(OPTIONAL_GATES)}（关卡3 摩擦所有研究线都必须真跑），"
            f"不认识 {unknown_stages}"
        )
    gate_modes = {}
    for gate in OPTIONAL_GATES:
        mode = stages.get(gate, {}).get("mode", "run")
        if mode not in GATE_MODES:
            raise SystemExit(f"track {track_id!r}：stages.{gate}.mode={mode!r} 不合法，可选 {list(GATE_MODES)}")
        gate_modes[gate] = mode
    synthesis_passthrough = {**DEFAULT_SYNTHESIS_PASSTHROUGH, **stages.get("synthesis", {}).get("passthrough", {})}

    report = raw.get("report", {})
    return Track(
        id=track_id,
        dir=track_dir,
        description=raw.get("description", ""),
        alpha_modules=tuple(modules),
        alpha_family=alphas.get("family"),
        tradable=tradable,
        neutralize=bool(preprocess.get("neutralize", True)),
        regime_dimensions=dimensions,
        matrix_top_k=int(report.get("matrix_top_k", 5)),
        min_abs_t=float(report.get("min_abs_t", 3.0)),
        gate_modes=gate_modes,
        synthesis_passthrough=synthesis_passthrough,
    )


_CLI_FIELDS = {
    "id", "dir", "profile_path", "results_dir", "handoff_dir", "neutralize", "matrix_top_k", "min_abs_t",
}


def _main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit(__doc__)
    track = load_track(argv[0])
    field_name = argv[1]
    if field_name.startswith("mode."):
        gate = field_name.split(".", 1)[1]
        if gate not in OPTIONAL_GATES:
            raise SystemExit(f"不支持的字段 {field_name!r}")
        print(track.gate_mode(gate))
        return
    if field_name not in _CLI_FIELDS:
        raise SystemExit(f"不支持的字段 {field_name!r}")
    value = getattr(track, field_name)
    # 布尔值按 shell 习惯输出小写，方便 [ "$(...)" = true ] 判断。
    print(str(value).lower() if isinstance(value, bool) else value)


if __name__ == "__main__":
    _main(sys.argv[1:])
