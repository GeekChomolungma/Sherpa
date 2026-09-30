# 研究线编排脚本（research/alpha_research/<track>/run_track.sh）共用的 bash 工具，只能被 source，不单独执行。
#
# 调用方在 source 之前设好 TRACK_DIR（研究线目录的绝对路径），可选设 TRACK_WITH_FLAGS（空格分隔，这条
# 研究线支持的可选步骤开关名，比如 "calibration"，对应命令行 --with-calibration）。source 之后：
#   track_init "$@"              解析 --from-step N / --dry-run / --with-<名字> / -h，设好 PYTHONPATH 等环境
#   with_flag <名字>             命令行给了 --with-<名字> 就返回真
#   require_ch_host 1 3 ...      列出要连 ClickHouse 的步骤号，会跑到其中任何一步却没设 CH_HOST 就提前退出
#   gate_db_steps <首个步骤号>   run_gate_stages 里要连库的步骤号（关卡1/2 透传时不连库），喂给 require_ch_host
#   track_get <字段>             读 track.json（字段见 research/_shared/track.py）
#   step <编号> <说明> <目录> <命令...>   在 <目录> 下执行一步；--from-step / --dry-run 在这里生效
#   run_research_stages <n>      阶段一体检（n）→ 汇总报告 + 候选集交接（n+1）
#   run_gate_stages <n>          关卡1（n）→ 关卡2（n+1）→ 关卡3（n+2），关卡1/2 真跑还是透传由 track.json 决定
#   track_done                   打印总用时和重点产出
#
# 提供的变量：ROOT（仓库根目录）、ROOT_NATIVE / TRACK_DIR_NATIVE（给 Windows python 用的原生路径）、
# PIPELINE_DIR、TRACK（研究线 id）、PYTHON。

set -Eeuo pipefail

# WSL 里跑会读不到 Windows 的环境变量（PowerShell 的 $env:CH_HOST），也没有装了 sherpa 的 Windows python。
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "检测到当前 bash 是 WSL，不是 Git Bash：读不到 PowerShell 里设的 \$env:CH_HOST，也没有你装了 sherpa 的 Windows python。" >&2
  echo "请改用 Git Bash 运行，例如：& \"D:\\Git\\bin\\bash.exe\" <run_track.sh 路径> <参数>" >&2
  exit 1
fi

: "${TRACK_DIR:?source lib.sh 之前要先设 TRACK_DIR}"
PIPELINE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$PIPELINE_DIR/../../.." && pwd)"
PYTHON="${PYTHON:-python}"
TRACK="$(basename "$TRACK_DIR")"

# Git Bash 下 python 是 Windows 程序，要用 Windows 风格路径和分号分隔；纯 Linux/mac 用原路径和冒号。
native_path() { (cd "$1" && pwd -W 2>/dev/null) || echo "$1"; }
ROOT_NATIVE="$(native_path "$ROOT")"
TRACK_DIR_NATIVE="$(native_path "$TRACK_DIR")"
if [ "$ROOT_NATIVE" != "$ROOT" ]; then SEP=";"; else SEP=":"; fi
export PYTHONPATH="$ROOT_NATIVE${PYTHONPATH:+$SEP$PYTHONPATH}"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

DRY=0
FROM=0
TRACK_WITH_FLAGS="${TRACK_WITH_FLAGS:-}"
WITH_ON=" "
CURRENT="(未开始)"
START=$SECONDS

# 打印调用方脚本开头那段注释（第 2 行起到第一个非注释行为止）。
_track_usage() { awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; }

track_init() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --dry-run) DRY=1 ;;
      --from-step) shift; FROM="${1:?--from-step 需要一个步骤编号}" ;;
      --with-*)
        local name="${1#--with-}"
        case " $TRACK_WITH_FLAGS " in
          *" $name "*) WITH_ON="$WITH_ON$name " ;;
          *) echo "这条研究线不支持 $1（支持：${TRACK_WITH_FLAGS:-无}）" >&2; exit 2 ;;
        esac ;;
      -h|--help) _track_usage; exit 0 ;;
      *) echo "未知参数: $1（用 -h 查看说明）" >&2; exit 2 ;;
    esac
    shift
  done
  trap _track_on_exit EXIT
  echo "[研究线] $TRACK（$TRACK_DIR）"
  echo "[研究配置] $(tr -d ' \r\n' < "$ROOT/research/research_config.json")"
  echo "[关卡模式] 关卡1=$(track_get mode.orthogonalization)，关卡2=$(track_get mode.synthesis)，关卡3=run；中性化=$(track_get neutralize)"
}

_track_on_exit() {
  local rc=$?
  if [ "$rc" -ne 0 ] && [ "$CURRENT" != "(未开始)" ] && [ "$CURRENT" != "(完成)" ]; then
    echo >&2
    echo "[FAIL] 失败于：$CURRENT（退出码 $rc）" >&2
    echo "       修好后可用 --from-step N 从失败的那一步继续，不用从头重跑。" >&2
  fi
}

with_flag() { case "$WITH_ON" in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

require_ch_host() {
  [ "$DRY" -eq 1 ] && return 0
  local n
  for n in "$@"; do
    if [ "$n" -ge "$FROM" ] && [ -z "${CH_HOST:-}" ]; then
      echo "缺少环境变量 CH_HOST（步骤 $n 需要连 ClickHouse）。" >&2
      exit 1
    fi
  done
}

track_get() { "$PYTHON" "$ROOT/research/_shared/track.py" "$TRACK_DIR_NATIVE" "$1" | tr -d '\r'; }

step() {
  local n="$1" title="$2" dir="$3"; shift 3
  [ "$n" -ge "$FROM" ] || return 0
  CURRENT="步骤 $n · $title"
  echo
  echo "=================================================================="
  echo "  步骤 $n · $title"
  echo "  (cd ${dir#"$ROOT"/} && $*)"
  echo "=================================================================="
  [ "$DRY" -eq 1 ] && return 0
  ( cd "$dir" && "$@" )
}

# 通用流程分两段，各阶段之间只靠 <研究线>/handoff/*.json 交接（research/_shared/handoff.py）：
#   run_research_stages <n>：阶段一体检（步骤 n）→ 汇总报告，产出候选集交接文件（步骤 n+1）
#   run_gate_stages <n>    ：关卡1（n）→ 关卡2（n+1）→ 关卡3（n+2）
# 关卡1/2 是真跑还是透传由 track.json 的 stages 决定，编排脚本不用管——透传同样产出标准交接文件，下游感知不到差别。
# 分两段是为了让研究线需要时能在阶段一和关卡之间插自己的步骤。
run_research_stages() {
  local n="$1"
  local profile results handoff_dir min_abs_t
  profile="$(track_get profile_path)"
  results="$(track_get results_dir)"
  handoff_dir="$(track_get handoff_dir)"
  min_abs_t="${MIN_ABS_T:-$(track_get min_abs_t)}"

  step "$n" "阶段一 · Regime 条件 IC 体检" "$PIPELINE_DIR" "$PYTHON" run_profile.py "$TRACK_DIR_NATIVE"
  step $((n + 1)) "汇总报告 / 04_regime_matrix -> 候选集交接" "$ROOT/research/regime_factor_report"     "$PYTHON" regime_factor_report.py "$profile" --output-dir "$results/report"     --matrix-top-k "$(track_get matrix_top_k)" --min-abs-t "$min_abs_t"     --track "$TRACK" --handoff-out "$handoff_dir/report.json"
}

run_gate_stages() {
  local n="$1"
  local research="$ROOT/research"
  step "$n" "关卡1 · 因子正交化（$(track_get mode.orthogonalization)）" "$research/factor_orthogonalization"     "$PYTHON" run_orthogonalization.py --track "$TRACK_DIR_NATIVE"
  step $((n + 1)) "关卡2 · 合成方案对比（$(track_get mode.synthesis)）" "$research/factor_synthesis"     "$PYTHON" run_synthesis.py --track "$TRACK_DIR_NATIVE"
  step $((n + 2)) "关卡3 · 扣费回测" "$research/friction_test"     "$PYTHON" run_friction.py --track "$TRACK_DIR_NATIVE"
}

# run_gate_stages <n> 里要连 ClickHouse 的步骤号（关卡1/2 透传时不连库），喂给 require_ch_host。
gate_db_steps() {
  local n="$1" steps=""
  if [ "$(track_get mode.orthogonalization)" = run ]; then steps="$steps $n"; fi
  if [ "$(track_get mode.synthesis)" = run ]; then steps="$steps $((n + 1))"; fi
  echo "$steps $((n + 2))"
}

track_done() {
  CURRENT="(完成)"
  local results handoff_dir
  results="$(track_get results_dir)"
  handoff_dir="$(track_get handoff_dir)"
  echo
  echo "=================================================================="
  echo "  研究线 $TRACK 全部完成，用时 $(( (SECONDS - START) / 60 )) 分 $(( (SECONDS - START) % 60 )) 秒"
  echo "  重点产出（都在研究线目录下）："
  echo "    $(track_get profile_path)"
  echo "    $results/report/04_regime_matrix.csv                          每个 state 的 Top 因子"
  echo "    $results/orthogonalization/02_regime_cluster_assignments.csv  关卡1 保留/剔除（透传时没有）"
  echo "    $results/synthesis/01_scheme_comparison.csv                   关卡2 各方案验证段对比（透传时没有）"
  echo "    $results/friction/02_validation_base_cost.csv                 关卡3 验证段扣费回测排名"
  echo "    $handoff_dir/                                                 各阶段交接文件（可手改后 --from-step 续跑）"
  echo "=================================================================="
}
