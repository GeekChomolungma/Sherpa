#!/usr/bin/env bash
# tradecraft 研究线编排：交易经验 alpha（sherpa/alpha/custom/tradecraft/，写法见那里的 README.md）。
# 研究线配置见同目录 track.json；产出按 run 归档在 runs/<run_id>/ 下，run_id 默认 = 参评 alpha 的 name（tc_xxx），
# 不同 alpha、不同版本互不覆盖。规则直接打分、不训练，没有模型文件。
#
# 需要先设好 ClickHouse 连接环境变量（只有 CH_HOST 是必填），用 Git Bash 跑：
#   bash research/alpha_research/tradecraft/run_track.sh --alphas custom.tc_xxx
#
# 流程（各阶段只靠 handoff/*.json 交接；关卡1/2 透传，alpha 打分直接变成单因子配方）：
#   0  逐期 RankIC 时间线             -> runs/<run_id>/results/ic_timeline/（整个研究段每根 bar 的 RankIC，横比主判据，
#                                        格式同 MLalpha 的 ml_training/*_ic_by_bar.csv，research/viz/ 直接能画）
#   1  阶段一 · Regime 条件 IC 体检   -> runs/<run_id>/regime_alpha_profile_without_neutralization.csv
#   2  汇总报告                        -> runs/<run_id>/results/report/ + handoff/report.json
#   3  关卡1 · 正交化（透传）
#   4  关卡2 · 合成（透传）
#   5  关卡3 · 扣费回测                -> runs/<run_id>/results/friction/
#   6  只做多回测（附加）              -> runs/<run_id>/results/long_only/（Top-K 只买不卖空、调仓每 2 / 3 根，跟等权基准比；
#                                        关卡3 的组合都是多空对称的、不改，这一步单独算，见 run_long_only.py）
#
# 本线 neutralize=false、流动性掩码跟 MLalpha 相同（成交额前一半），所以结果能直接跟 MLalpha 的 runs 横比、画在一张图上。
# report.min_abs_t = 0：每条经验规则都走到关卡3，强弱看 RankIC，不在阶段一按显著性挡掉。
# 注意关卡1/2 透传时，配方方向取阶段一（选择段）IC 的符号：规则在选择段 IC 为负，关卡3 会把它反过来做。步骤 0 的
# RankIC 永远按 alpha 自己的方向（越大越看多）算，方向错了在那里直接是负数。
#
# 参数：
#   --alphas a,b     这次评估哪些 alpha（qualified_name，逗号分隔），不写 = track.json 的 alphas.include
#                    例：--alphas custom.tc_demo_reversal   -> runs/tc_demo_reversal/
#   --variant <名字> 非默认设置的变体（比如临时改了 research_config.json）：run_id 加 __<名字>
#   --from-step N    从第 N 步开始
#   --dry-run        只打印每一步要执行的命令，不真的跑
#   -h | --help      显示本说明

TRACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$TRACK_DIR/../_pipeline/lib.sh"
track_init "$@"
# shellcheck disable=SC2046
require_ch_host 0 1 $(gate_db_steps 3) 6

step 0 "逐期 RankIC 时间线" "$PIPELINE_DIR" "$PYTHON" run_ic_timeline.py "$TRACK_DIR_NATIVE"
run_research_stages 1
run_gate_stages 3
step 6 "只做多回测（Top-K 只买、跟等权基准比）" "$TRACK_DIR" "$PYTHON" run_long_only.py "$TRACK_DIR_NATIVE"

track_done
