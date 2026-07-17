#!/bin/bash

# result_100M_edbt 用実験スクリプト
# 各ワークロードパターン（_16_2_10, _16_mono, _16_peak）に対して
# Dynamic(pruning有/無), Static(average), Adaptive(w=4) を実行し
# 結果を time_dependent_output/job/result_100M_edbt/ に集約する
#
# 使い方: bash scripts/shell/run_16_ab.sh
#         nohup bash scripts/shell/run_16_ab.sh > run_16_ab.log 2>&1 &

set -e

SCRIPT_DIR="scripts"

echo ""
echo "------------------------------------------------------------------------"
echo "[_16_2_10] Dynamic (pruning なし) → _wo にリネーム"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 6 \
  --query-set job-ceb-2 \
  --optimization-mode dynamic \
  --exp-suffix _48_mono \
  --noise-ratio 0.0 \
  --b-max 500 \
  --recalc \
  --use-docker 
echo "完了時刻: $(date)"


