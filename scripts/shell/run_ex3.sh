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
OUTPUT_DIR="time_dependent_output/ex3/log"
RESULT_DIR="time_dependent_output/ex3"
BASE_DIR="time_dependent_output/job-ceb-2"

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
echo "[_16_2_10] Dynamic (pruning なし) → _wo にリネーム"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job-ceb-2 \
  --optimization-mode dynamic \
  --exp-suffix _24_2_10 \
  --noise-ratio 0.0 \
  --b-max 500 \
  --recalc \
  --use-docker \
  --ease
rename_to_wo _24_2_10
echo "完了時刻: $(date)"


# ======================================================================
# _16_mono
# ======================================================================

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_mono] Dynamic (pruning なし) → _wo にリネーム"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job-ceb-2 \
  --optimization-mode dynamic \
  --exp-suffix _24_mono \
  --noise-ratio 0.0 \
  --b-max 500 \
  --recalc \
  --use-docker \
  --ease
rename_to_wo _24_mono
echo "完了時刻: $(date)"

# ======================================================================
# _16_peak
# ======================================================================

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_peak] Dynamic (pruning なし) → _wo にリネーム"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job-ceb-2 \
  --optimization-mode dynamic \
  --exp-suffix _24_peak \
  --noise-ratio 0.0 \
  --b-max 500 \
  --recalc \
  --use-docker \
  --ease
rename_to_wo _24_peak
echo "完了時刻: $(date)"


# ======================================================================
# Redbench_synthetic
# ======================================================================


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[Redbench_synthetic] Dynamic (pruning なし) → _wo にリネーム"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set Redbench_synthetic \
  --optimization-mode dynamic \
  --exp-suffix _2h_x2_50x \
  --noise-ratio 0.0 \
  --b-max 500 \
  --recalc \
  --use-docker \
  --ease
echo "完了時刻: $(date)"



echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "結果: ${RESULT_DIR}"
echo "========================================================================"
