#!/usr/bin/env bash
# 一键跑 research/ 全流程（阶段一 -> 关卡1 -> 关卡2 候选池），按依赖顺序依次执行，任何一步失败立刻停下。
#
# 需要先设好 ClickHouse 连接环境变量（只有 CH_HOST 是必填）：
#   bash / Git Bash :  export CH_HOST=... CH_PASSWORD=...
#   PowerShell      :  $env:CH_HOST="..."; $env:CH_PASSWORD="..."; & "D:\Git\bin\bash.exe" run_research.sh --from-step 3
#                      （别直接敲 bash：PowerShell 里的 bash 常常解析成 WSL，读不到 $env: 变量，用的也是 Linux python）
#
# 默认流程（每一步的产出都落在各自脚本所在目录，不再散落在仓库根目录）：
#   1  run_regime_report.py          -> alpha_research/worldquant_101/regime_report.csv
#   2  run_screening.py              -> alpha_research/worldquant_101/screening_report.csv
#   3  run_alpha_regime_profile.py   -> alpha_research/worldquant_101/regime_alpha_profile.csv
#                                       （是否中性化由该脚本顶部的 USE_NEUTRALIZATION 开关决定）
#   4  regime_factor_report.py       -> regime_factor_report/results/（含 04_regime_matrix.csv；
#                                       每个 state 只收 |t| >= MIN_ABS_T 的显著因子，再按 |IC_IR| 取 Top5）
#   7  run_orthogonalization.py      -> factor_orthogonalization/results/
#
# 可选步骤（默认不跑）：
#   --with-calibration     步骤0  tradability_calibration 三个脚本（流动性掩码门槛校准，纯参考）
#   --with-vectorized      步骤5  四个分类的单因子迷你回测（慢，辅助参考，不是必经步骤）
#   --refresh-candidates   步骤6  用刚生成的 04_regime_matrix.csv Top5 重写正交化的候选池
#                                 （config.py 里 REGIME_ALPHA_SETS 是手动维护的，因子公式/窗口
#                                  改过之后旧名单会过期；不加这个开关就沿用 config.py 现有名单）
#   --refresh-synthesis-candidates
#                          步骤8  用关卡1 刚生成的 02_regime_cluster_assignments.csv 里 keep 的因子
#                                 重写关卡2（factor_synthesis/config.py）的候选池，作为关卡2 的入口
#
# 其它：
#   --from-step N          从第 N 步开始（某一步失败后修好了，不用从头再跑）
#   --dry-run              只打印每一步要执行的命令，不真的跑
#   -h | --help            显示本说明

set -Eeuo pipefail

# WSL 里跑会读不到 Windows 的环境变量（PowerShell 的 $env:CH_HOST），而且用的是 Linux python，
# 缺 sherpa 依赖——直接拦下来说清楚，比后面报一个"缺少 CH_HOST"的误导性错误强。
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "检测到当前 bash 是 WSL，不是 Git Bash：读不到 PowerShell 里设的 \$env:CH_HOST，也没有你装了 sherpa 的 Windows python。" >&2
  echo "请改用 Git Bash 运行，例如（路径按你的 Git 安装位置改）：" >&2
  echo '  & "D:\Git\bin\bash.exe" run_research.sh <参数>' >&2
  exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-python}"
# 04_regime_matrix.csv 的显著性门槛（IC 均值 Newey–West t 值的绝对值）。标准和理由见
# QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md §3.1；设成 0 等于关掉门槛（只按 |IC_IR| 排名，旧行为）。
MIN_ABS_T="${MIN_ABS_T:-3.0}"

WITH_CAL=0
WITH_VEC=0
REFRESH=0
REFRESH_SYNTH=0
DRY=0
FROM=0

# 打印开头那段注释（从第 2 行到第一个非注释行为止），以后增删说明行不用再改这里的行号。
usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "${BASH_SOURCE[0]}"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --with-calibration) WITH_CAL=1 ;;
    --with-vectorized) WITH_VEC=1 ;;
    --refresh-candidates) REFRESH=1 ;;
    --refresh-synthesis-candidates) REFRESH_SYNTH=1 ;;
    --dry-run) DRY=1 ;;
    --from-step) shift; FROM="${1:?--from-step 需要一个步骤编号}" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1（用 -h 查看说明）" >&2; exit 2 ;;
  esac
  shift
done

ALPHA_DIR="$ROOT/research/alpha_research/worldquant_101"
REPORT_DIR="$ROOT/research/regime_factor_report"
ORTHO_DIR="$ROOT/research/factor_orthogonalization"
CAL_DIR="$ROOT/research/tradability_calibration"
SYNTH_DIR="$ROOT/research/factor_synthesis"

# 脚本内部用 `from data import ...` 和 sherpa 包；设好 PYTHONPATH 保证 sherpa 一定能 import
# （Git Bash 下要用 Windows 风格路径和分号分隔，纯 Linux/mac 用冒号）。
if ROOT_NATIVE="$(cd "$ROOT" && pwd -W 2>/dev/null)"; then SEP=";"; else ROOT_NATIVE="$ROOT"; SEP=":"; fi
export PYTHONPATH="$ROOT_NATIVE${PYTHONPATH:+$SEP$PYTHONPATH}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

will_run() {  # will_run <步骤号>：这一步在当前参数下会不会执行
  local n="$1"
  [ "$n" -ge "$FROM" ] || return 1
  case "$n" in
    0) [ "$WITH_CAL" -eq 1 ] ;;
    5) [ "$WITH_VEC" -eq 1 ] ;;
    6) [ "$REFRESH" -eq 1 ] ;;
    8) [ "$REFRESH_SYNTH" -eq 1 ] ;;
    *) return 0 ;;
  esac
}

# 需要连 ClickHouse 的步骤：0 1 2 3 5 7。提前检查，别跑了半小时才发现没设环境变量。
if [ "$DRY" -eq 0 ]; then
  for n in 0 1 2 3 5 7; do
    if will_run "$n" && [ -z "${CH_HOST:-}" ]; then
      echo "缺少环境变量 CH_HOST（步骤 $n 需要连 ClickHouse）。设置方法见本脚本开头的说明。" >&2
      exit 1
    fi
  done
fi

CURRENT="(未开始)"
# 用 EXIT 而不是 ERR：子 shell 里的失败会让 ERR 在子 shell 和父 shell 各触发一次，提示会打两遍。
on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ] && [ "$CURRENT" != "(未开始)" ] && [ "$CURRENT" != "(完成)" ]; then
    echo >&2
    echo "[FAIL] 失败于：$CURRENT（退出码 $rc）" >&2
    echo "       修好后可用 --from-step N 从失败的那一步继续，不用从头重跑。" >&2
  fi
}
trap on_exit EXIT

step() {  # step <编号> <说明> <目录> <命令...>
  local n="$1" title="$2" dir="$3"; shift 3
  will_run "$n" || return 0
  CURRENT="步骤 $n · $title"
  echo
  echo "=================================================================="
  echo "  步骤 $n · $title"
  echo "  (cd ${dir#"$ROOT"/} && $*)"
  echo "=================================================================="
  [ "$DRY" -eq 1 ] && return 0
  ( cd "$dir" && "$@" )
}

START=$SECONDS

# 提示当前是不是中性化模式（run_alpha_regime_profile.py 顶部的开关），以及下游读哪份 CSV。
PROFILE_CSV="regime_alpha_profile.csv"
REPORT_OUT="results"
if grep -Eq '^USE_NEUTRALIZATION[[:space:]]*=[[:space:]]*False' "$ALPHA_DIR/run_alpha_regime_profile.py"; then
  PROFILE_CSV="regime_alpha_profile_without_neutralization.csv"
  REPORT_OUT="results_without_neutralization"
  echo "[注意] run_alpha_regime_profile.py 里 USE_NEUTRALIZATION=False：本次是【原始分数/未剥离 Beta】"
  echo "       对照模式，汇总报告写到 regime_factor_report/$REPORT_OUT/，不会覆盖 results/，"
  echo "       后面的候选池刷新/正交化也不建议基于这一版。"
else
  echo "[模式] 中性化（剥离 Beta/Size）：USE_NEUTRALIZATION=True"
fi
# 各步骤的取数区间（window）和 IC 标签口径（label）统一来自 research/research_config.json，打印出来方便核对。
echo "[研究配置] $(tr -d ' \r\n' < "$ROOT/research/research_config.json")"
echo "[显著性门槛] 04_regime_matrix 只收 |t| >= $MIN_ABS_T 的因子（环境变量 MIN_ABS_T 可调）"

step 0 "流动性掩码校准 · 分布研究"   "$CAL_DIR" "$PYTHON" run_distribution_study.py
step 0 "流动性掩码校准 · 分位数敏感性" "$CAL_DIR" "$PYTHON" run_percentile_sensitivity.py
step 0 "流动性掩码校准 · 绝对地板敏感性" "$CAL_DIR" "$PYTHON" run_floor_sensitivity.py

step 1 "Regime 打标"                 "$ALPHA_DIR" "$PYTHON" run_regime_report.py
step 2 "全局筛选（第一层 IC 体检）"   "$ALPHA_DIR" "$PYTHON" run_screening.py
step 3 "Regime 条件 IC 体检"          "$ALPHA_DIR" "$PYTHON" run_alpha_regime_profile.py
step 4 "汇总报告 / 04_regime_matrix"  "$REPORT_DIR" "$PYTHON" regime_factor_report.py \
  "$ROOT_NATIVE/research/alpha_research/worldquant_101/$PROFILE_CSV" --output-dir "$REPORT_OUT" --matrix-top-k 5 \
  --min-abs-t "$MIN_ABS_T"

if will_run 5; then
  for fam in price_volume momentum_reversal microstructure composite; do
    step 5 "单因子迷你回测 · $fam" "$ALPHA_DIR/$fam" "$PYTHON" run_vectorized.py
  done
fi

step 6 "刷新正交化候选池（04 矩阵 Top5 -> config.py）" "$ORTHO_DIR" "$PYTHON" refresh_candidates.py --top-k 5

if will_run 7 && [ "$REFRESH" -eq 0 ]; then
  echo
  echo "[提示] 正交化沿用 factor_orthogonalization/config.py 里手动维护的候选池，没有跟着刚生成的"
  echo "       04_regime_matrix.csv 更新。如果上游因子公式/窗口刚改过，建议加 --refresh-candidates。"
fi
step 7 "关卡1 · 因子正交化聚类"        "$ORTHO_DIR" "$PYTHON" run_orthogonalization.py

step 8 "关卡2 入口 · 刷新合成候选池（02 keep 名单 -> factor_synthesis/config.py）" \
  "$SYNTH_DIR" "$PYTHON" refresh_candidates.py

CURRENT="(完成)"
echo
echo "=================================================================="
echo "  全部完成，用时 $(( (SECONDS - START) / 60 )) 分 $(( (SECONDS - START) % 60 )) 秒"
echo "  重点产出："
echo "    research/regime_factor_report/$REPORT_OUT/04_regime_matrix.csv   每个 state 的 Top 因子"
echo "    research/factor_orthogonalization/results/02_regime_cluster_assignments.csv   关卡1 保留/剔除建议"
if [ "$REFRESH_SYNTH" -eq 1 ]; then
  echo "    research/factor_synthesis/config.py   关卡2 候选池（已按关卡1 keep 名单刷新）"
fi
echo "=================================================================="
