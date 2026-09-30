#!/usr/bin/env bash
# 兼容入口：转发到世坤101 研究线自己的编排脚本 research/alpha_research/worldquant_101/run_track.sh。
#
# research/ 现在按研究线（track）组织：每条研究线在 research/alpha_research/<track>/ 下有自己的 track.json
# 和 run_track.sh，产出都归档在研究线目录里；各关卡之间靠 handoff/*.json 自动交接。说明见
# research/alpha_research/README.md。其它研究线直接跑它自己的 run_track.sh，比如：
#   bash research/alpha_research/custom_starter/run_track.sh
#
# 跟旧版的区别：
#   - 旧的 --refresh-candidates / --refresh-synthesis-candidates / --refresh-friction-cases 已经没有意义
#     （上游阶段自己产出标准交接文件，下游直接读），这里收到会提示后忽略；
#   - 步骤编号变了（跟其它研究线统一）：1 阶段一、2 报告、3 关卡1、4 关卡2、5 关卡3。
#     --from-step 用新编号，完整说明见 worldquant_101/run_track.sh -h；
#   - 世坤专属的旧步骤（regime 打标报告、全局筛选、分类单因子迷你回测）已删除，--with-screening /
#     --with-vectorized 收到会提示后忽略；流动性校准 --with-calibration 保留。
# 其余参数（--with-calibration / --from-step / --dry-run / -h）原样透传。

set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$ROOT/research/alpha_research/worldquant_101/run_track.sh"

args=()
while [ $# -gt 0 ]; do
  case "$1" in
    --refresh-candidates|--refresh-synthesis-candidates|--refresh-friction-cases)
      echo "[提示] $1 已废弃：各阶段通过 handoff/*.json 自动交接，不再需要刷新候选池，忽略这个参数。" >&2 ;;
    --with-screening|--with-vectorized)
      echo "[提示] $1 已废弃：对应的世坤专属旧步骤已删除（全局筛选由报告的 05 矩阵覆盖，单因子回测由关卡3 覆盖），忽略这个参数。" >&2 ;;
    --from-step)
      args+=("$1" "${2:?--from-step 需要一个步骤编号}")
      case "$2" in
        6|7|8|9|10|11) echo "[提示] 步骤编号已变：现在是 1 阶段一、2 报告、3 关卡1、4 关卡2、5 关卡3，请确认 --from-step $2 是你要的。" >&2 ;;
      esac
      shift ;;
    *) args+=("$1") ;;
  esac
  shift
done

exec bash "$TARGET" "${args[@]+"${args[@]}"}"
