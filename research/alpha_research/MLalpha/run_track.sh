#!/usr/bin/env bash
# MLalpha 研究线编排：机器学习模型 alpha（sherpa/alpha/custom/ml/，设计见 sherpa/alpha/custom/ML_ALPHA_DESIGN.md）。
# 研究线配置见同目录 track.json；模型文件在 models/<模型名>/（不进 git，manifest.json 进），其余产出在 results*/ 和 handoff*/ 下。
#
# 需要先设好 ClickHouse 连接环境变量（只有 CH_HOST 是必填），用 Git Bash 跑：
#   bash research/alpha_research/MLalpha/run_track.sh [参数]
#
# 流程（各阶段只靠 handoff/*.json 交接；本线关卡1/2 都透传，模型打分直接变成权重 +1 的单因子配方）：
#   0  滚动训练                        -> models/<模型名>/ + results/ml_training/（每个重训时点的样本外 RankIC）
#   1  阶段一 · Regime 条件 IC 体检   -> regime_alpha_profile.csv（这里的 regime 切片只做诊断，不决定方向）
#   2  汇总报告                        -> results/report/ + handoff/report.json
#   3  关卡1 · 正交化（透传）
#   4  关卡2 · 合成（透传）
#   5  关卡3 · 扣费回测                -> results/friction/
#
# 本线 neutralize=false（标签默认不中性化，外层也不做），所以 results / handoff 目录都带 _without_neutralization 后缀。
# 步骤 0 是增量的：已经训练好的重训时点直接跳过；特征清单或训练配置（research/ml_training/config.py）变了会拒绝续训，
# 要全部重训就单独跑 `python research/ml_training/run_training.py --track MLalpha --force`。
#
# 参数：
#   --from-step N    从第 N 步开始（比如模型已经训练好，--from-step 1 直接评估）
#   --dry-run        只打印每一步要执行的命令，不真的跑
#   -h | --help      显示本说明

TRACK_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$TRACK_DIR/../_pipeline/lib.sh"
track_init "$@"
# shellcheck disable=SC2046
require_ch_host 0 1 $(gate_db_steps 3)

# 每次都先校验：模型 spec.liquidity（训练 / 推断用的流动性范围）== 本研究线 track.json 的评估掩码。
# 不受 --from-step / --dry-run 影响——改了 track.json 再 --from-step 1 只做评估时，也会在这里拦住，
# 不会拿旧模型在另一个掩码下评估。只读配置，不取数、不训练，几秒钟。
( cd "$ROOT/research/ml_training" && "$PYTHON" run_training.py --track "$TRACK_DIR_NATIVE" --check-only )

step 0 "滚动训练" "$ROOT/research/ml_training" "$PYTHON" run_training.py --track "$TRACK_DIR_NATIVE"
run_research_stages 1
run_gate_stages 3

track_done
