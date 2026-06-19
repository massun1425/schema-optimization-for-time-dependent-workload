#!/bin/bash

# result_100M_edbt 用実験スクリプト
# 各周期設定（_16_1_10, _16_2_10, _16_3_10, _16_mono, _16_peak）に対して
# Dynamic(pruning有/無), Static(average), Adaptive(w=4) を実行し
# 結果を time_dependent_output/job/result_100M_edbt/ に集約する
#
# 使い方: bash scripts/shell/run_16_ab.sh
#         nohup bash scripts/shell/run_16_ab.sh > run_16_ab.log 2>&1 &

set -e

SCRIPT_DIR="scripts"
OUTPUT_DIR="time_dependent_output/ex1_1/log"
RESULT_DIR="time_dependent_output/ex1_1"
BASE_DIR_JOB="time_dependent_output/job"
BASE_DIR_REDBENCH="time_dependent_output/Redbench_synthetic"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

mkdir -p ${OUTPUT_DIR}
mkdir -p ${RESULT_DIR}

restart_container() {
    echo ""
    echo ">>> PostgreSQLコンテナを再起動してキャッシュをクリア..."
    docker restart mv_postgres
    echo ">>> 起動完了を待機中..."
    sleep 15
    until docker exec mv_postgres pg_isready -U postgres > /dev/null 2>&1; do
        echo ">>> PostgreSQL起動待ち..."
        sleep 2
    done
    echo ">>> PostgreSQL起動完了"
}

# pruning なし実行後に結果ファイルを _wo にリネームする関数
rename_to_wo() {
    local suffix=$1  # 例: _16_1_10
    mv -f ${BASE_DIR}/td_mv_optimization_result${suffix}.json \
          ${BASE_DIR}/td_mv_optimization_result${suffix}_wo.json
    mv -f ${BASE_DIR}/benchmark_results_dynamic${suffix}.json \
          ${BASE_DIR}/benchmark_results_dynamic${suffix}_wo.json
}

# ======================================================================
# _16_2_10
# ======================================================================


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_2_10] Adaptive (w=4)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode peloton \
  --window-size 4 \
  --exp-suffix _16_2_10 \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  --ease
echo "完了時刻: $(date)"