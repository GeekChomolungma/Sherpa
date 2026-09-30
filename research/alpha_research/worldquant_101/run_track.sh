#!/usr/bin/env bash
# worldquant_101 研究线编排：世坤101 全量因子的完整流程（阶段一 -> 关卡1 -> 关卡2 -> 关卡3），全流程样板。
# 研究线配置见同目录 track.json；全部产出都归档在本目录的 results/ 和 handoff/ 下，各关卡目录只放代码。
# 按依赖顺序依次执行，任何一步失败立刻停下。
#
# 需要先设好 ClickHouse 连接环境变量（只有 CH_HOST 是必填），用 Git Bash 跑：
#   bash / Git Bash :  export CH_HOST=... CH_PASSWORD=...
#   PowerShell      :  $env:CH_HOST="..."; $env:CH_PASSWORD="..."; & "D:\Git\bin\bash.exe" research/alpha_research/worldquant_101/run_track.sh
#                      （别直接敲 bash：PowerShell 里的 bash 常常解析成 WSL，读不到 $env: 变量，用的也是 Linux python）
#
# 流程（各阶段之间只靠 handoff/*.json 交接，见 research/_shared/handoff.py；本线关卡1/2 都真跑）：
#   1  阶段一 · Regime 条件 IC 体检  -> regime_alpha_profile.csv
#   2  汇总报告                      -> results/report/（含 04/05 矩阵）+ handoff/report.json（候选集）
#   3  关卡1 · 因子正交化聚类        -> results/orthogonalization/ + handoff/orthogonalization.json（去冗余后的候选集）
#   4  关卡2 · 合成方案对比          -> results/synthesis/ + handoff/synthesis.json（交给关卡3 的配方集）
#   5  关卡3 · 扣费回测              -> results/friction/
#
# 时间切分（research/research_config.json 的 window）：步骤 1~3 只用选择段（截止 validation_start），
# 步骤 4、5 用整个研究段（选择段估方向 / 定配方、验证段比较），holdout 全程不碰。
# 研究线口径（因子范围、是否中性化、regime 维度、报告门槛、关卡1/2 真跑还是透传）都在 track.json。
#
# 想手动干预某一关的输入（比如删掉某个候选因子）：直接改 handoff/ 下对应的 json，再 --from-step 下一步。
#
# 参数：
#   --with-calibration     步骤0  先跑 tradability_calibration 三个脚本（流动性掩码门槛校准，纯参考，默认不跑）
#   MIN_ABS_T=...          环境变量，临时覆盖 track.json 的 report.min_abs_t（设成 0 = 关掉显著性门槛）
#   --from-step N          从第 N 步开始（某一步失败后修好了，不用从头再跑）
#   --dry-run              只打印每一步要执行的命令，不真的跑
#   -h | --help            显示本说明

TRACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRACK_WITH_FLAGS="calibration"
source "$TRACK_DIR/../_pipeline/lib.sh"
track_init "$@"

db_steps="1 $(gate_db_steps 3)"
if with_flag calibration; then db_steps="0 $db_steps"; fi
# shellcheck disable=SC2086
require_ch_host $db_steps

if with_flag calibration; then
  CAL_DIR="$ROOT/research/tradability_calibration"
  step 0 "流动性掩码校准 · 分布研究"     "$CAL_DIR" "$PYTHON" run_distribution_study.py
  step 0 "流动性掩码校准 · 分位数敏感性" "$CAL_DIR" "$PYTHON" run_percentile_sensitivity.py
  step 0 "流动性掩码校准 · 绝对地板敏感性" "$CAL_DIR" "$PYTHON" run_floor_sensitivity.py
fi

run_research_stages 1
run_gate_stages 3

track_done
