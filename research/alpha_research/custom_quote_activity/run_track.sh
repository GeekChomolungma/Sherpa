#!/usr/bin/env bash
# custom_quote_activity 研究线编排：成交活跃度排名单因子（sherpa/alpha/custom/quote_activity.py），只看 trend 维度。
# 研究线配置见同目录 track.json；全部产出都归档在本目录的 results/ 和 handoff/ 下。
#
# 需要先设好 ClickHouse 连接环境变量（只有 CH_HOST 是必填），用 Git Bash 跑：
#   bash research/alpha_research/custom_quote_activity/run_track.sh [参数]
#
# 流程（各阶段只靠 handoff/*.json 交接；关卡1/2 真跑还是透传看 track.json 的 stages，本线两关都透传）：
#   1  阶段一 · Regime 条件 IC 体检   -> regime_alpha_profile.csv
#   2  汇总报告                        -> results/report/（含 04_regime_matrix.csv） + handoff/report.json
#   3  关卡1 · 正交化（透传）          -> handoff/orthogonalization.json
#   4  关卡2 · 合成（透传：候选集直接变成等权配方）-> handoff/synthesis.json
#   5  关卡3 · 扣费回测                -> results/friction/
#
# 参数：
#   --from-step N    从第 N 步开始（比如手改了某个 handoff/*.json 之后，从下一步续跑）
#   --dry-run        只打印每一步要执行的命令，不真的跑
#   -h | --help      显示本说明

TRACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$TRACK_DIR/../_pipeline/lib.sh"
track_init "$@"
# shellcheck disable=SC2046
require_ch_host 1 $(gate_db_steps 3)

run_research_stages 1
run_gate_stages 3

track_done
