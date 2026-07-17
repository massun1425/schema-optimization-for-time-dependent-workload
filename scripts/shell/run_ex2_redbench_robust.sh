#!/bin/bash

# time_dependent_output/Redbench_synthetic/result_100M 用実験スクリプト
# suffix: _2h_x2
# クエリセット: Redbench_synthetic
#
# 実行内容:
#   - Dynamic (pruning あり)
#   - Dynamic nocon (親制約なし)
#   - Static (average)
#   - Adaptive (w=4)
#   - Dynamic noise benchmark (5%, 10%, ..., 40%)
#   - Static noise benchmark (5%, 10%, ..., 40%)
#
# 使い方: bash scripts/shell/run_experiment_job.sh
#         nohup bash scripts/shell/run_experiment_job.sh > run_experiment_job.log 2>&1 &

set -e

SCRIPT_DIR="scripts"
QUERY_SET="Redbench_synthetic"
SUFFIX="_2h_x2_50x"
OUTPUT_DIR="time_dependent_output/ex2/log"
RESULT_DIR="time_dependent_output/ex2"
BASE_DIR="time_dependent_output/Redbench_synthetic"

echo "========================================================================"
echo "実験開始: $(date)"
echo "クエリセット: ${QUERY_SET} / suffix: ${SUFFIX}"
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

# ======================================================================
# Dynamic (pruning あり)
# ======================================================================

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "Dynamic (pruning あり)"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set ${QUERY_SET} \
#   --optimization-mode dynamic \
#   --exp-suffix ${SUFFIX} \
#   --use-pruning \
#   --pruning-parallel \
#   --noise-ratio 0.45 \
#   --b-max 500 \
#   --recalc \
#   --use-docker \
#   --ease
# echo "完了時刻: $(date)"


# ======================================================================
# Static (average)
# ======================================================================

# restart_container
# echo ""
# echo "------------------------------------------------------------------------"
# echo "Static (average)"
# echo "開始時刻: $(date)"
# echo "------------------------------------------------------------------------"
# python ${SCRIPT_DIR}/run_experiment_normal.py \
#   --phase post-opt \
#   --query-set ${QUERY_SET} \
#   --optimization-mode static \
#   --static-timestep average \
#   --static-algorithm utility \
#   --exp-suffix ${SUFFIX} \
#   --noise-ratio 0.05 \
#   --b-max 500 \
#   --recalc \
#   --use-docker \
#   --ease
# echo "完了時刻: $(date)"



# ======================================================================
# Dynamic noise benchmark (phase 9 のみ、最適化結果は _2h_x2 を使用)
# --noise-ratio X を指定すると出力ファイル名に _noise{N} が自動付与される
# ======================================================================

# for NOISE in 0.50; do
#     NOISE_LABEL=$(echo "${NOISE} * 100" | bc | sed 's/\.00//')
#     restart_container
#     echo ""
#     echo "------------------------------------------------------------------------"
#     echo "Dynamic noise benchmark (noise=${NOISE_LABEL}%)"
#     echo "開始時刻: $(date)"
#     echo "------------------------------------------------------------------------"
#     python ${SCRIPT_DIR}/run_experiment_normal.py \
#       --phase 9 \
#       --query-set ${QUERY_SET} \
#       --benchmark-mode dynamic \
#       --exp-suffix ${SUFFIX} \
#       --noise-ratio ${NOISE} \
#       --use-docker \
#       --ease
#     echo "完了時刻: $(date)"
# done

# ======================================================================
# Static noise benchmark (phase 9 のみ)
# ======================================================================

for NOISE in 0.10 0.15 0.20 0.25 0.30 0.35 0.40 0.45 0.50; do
    NOISE_LABEL=$(echo "${NOISE} * 100" | bc | sed 's/\.00//')
    restart_container
    echo ""
    echo "------------------------------------------------------------------------"
    echo "Static noise benchmark (noise=${NOISE_LABEL}%)"
    echo "開始時刻: $(date)"
    echo "------------------------------------------------------------------------"
    python ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase 9 \
      --query-set ${QUERY_SET} \
      --benchmark-mode static \
      --exp-suffix ${SUFFIX} \
      --noise-ratio ${NOISE} \
      --use-docker \
      --ease
    echo "完了時刻: $(date)"
done

# ======================================================================
# 結果を result_100M/ に集約
# ======================================================================

# echo ""
# echo "========================================================================"
# echo "結果を ${RESULT_DIR} に移動中..."
# echo "========================================================================"

# mv -f ${BASE_DIR}/td_mv_optimization_result${SUFFIX}*.json          ${RESULT_DIR}/ 2>/dev/null || true
# mv -f ${BASE_DIR}/static_mv_optimization_result${SUFFIX}*.json      ${RESULT_DIR}/ 2>/dev/null || true
# mv -f ${BASE_DIR}/adaptive_mv_optimization_result_w4${SUFFIX}*.json ${RESULT_DIR}/ 2>/dev/null || true
# mv -f ${BASE_DIR}/benchmark_results_dynamic${SUFFIX}*.json          ${RESULT_DIR}/ 2>/dev/null || true
# mv -f ${BASE_DIR}/benchmark_results_static${SUFFIX}*.json           ${RESULT_DIR}/ 2>/dev/null || true
# mv -f ${BASE_DIR}/benchmark_results_adaptive_w4${SUFFIX}*.json      ${RESULT_DIR}/ 2>/dev/null || true

echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "結果: ${RESULT_DIR}"
echo "========================================================================"
