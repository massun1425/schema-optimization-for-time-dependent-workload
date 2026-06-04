#!/bin/bash

# フェーズ6（最適化のみ）実験スクリプト
# _8_mono から _32_mono まで 4 刻みで
# Dynamic pruning なし（→ _wo にリネーム）と Dynamic pruning あり を実行し
# 結果を time_dependent_output/ex1_3/ に保存する
#
# 使い方: bash scripts/shell/run_ex1_3.sh
#         nohup bash scripts/shell/run_ex1_3.sh > run_ex1_3.log 2>&1 &

set -e

SCRIPT_DIR="scripts"
OUTPUT_DIR="time_dependent_output/ex1_3/log"
RESULT_DIR="time_dependent_output/ex1_3"
BASE_DIR="time_dependent_output/job"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

mkdir -p ${OUTPUT_DIR}
mkdir -p ${RESULT_DIR}

rename_to_wo() {
    local suffix=$1
    mv -f ${BASE_DIR}/td_mv_optimization_result${suffix}.json \
          ${BASE_DIR}/td_mv_optimization_result${suffix}_wo.json
}

for TS in 8 12 16 20 24 28 32; do
    SUFFIX="_${TS}_mono"

    echo ""
    echo "------------------------------------------------------------------------"
    echo "[${SUFFIX}] Dynamic (pruning なし) → _wo にリネーム"
    echo "開始時刻: $(date)"
    echo "------------------------------------------------------------------------"
    python ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase 6 \
      --query-set job \
      --optimization-mode dynamic \
      --exp-suffix ${SUFFIX} \
      --b-max 100 \
      --recalc \
      2>&1 | tee ${OUTPUT_DIR}/log_dynamic${SUFFIX}_wo.txt
    rename_to_wo ${SUFFIX}
    echo "完了時刻: $(date)"

    echo ""
    echo "------------------------------------------------------------------------"
    echo "[${SUFFIX}] Dynamic (pruning あり)"
    echo "開始時刻: $(date)"
    echo "------------------------------------------------------------------------"
    python ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase 6 \
      --query-set job \
      --optimization-mode dynamic \
      --exp-suffix ${SUFFIX} \
      --use-pruning \
      --b-max 100 \
      --recalc \
      2>&1 | tee ${OUTPUT_DIR}/log_dynamic${SUFFIX}.txt
    echo "完了時刻: $(date)"

done

echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "結果: ${RESULT_DIR}"
echo "========================================================================"
