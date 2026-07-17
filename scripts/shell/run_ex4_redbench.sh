#!/bin/bash

# 容量制約変化実験スクリプト
# B_max を 100, 1000, 1500, 2000 と変化させて post-opt を実行する
# 頻度: _16_2_10 / クエリセット: job
# 手法: Dynamic(pruning有), Static(average, utility), Adaptive(w=4)
# 各容量の結果は上書き回避のため容量別フォルダに移動する
#
# 使い方: bash scripts/shell/run_ex4.sh
#         nohup bash scripts/shell/run_ex4.sh > run_ex4.log 2>&1 &

set -e

SCRIPT_DIR="scripts"
SUFFIX="_2h_x2_50x"
BASE_DIR="time_dependent_output/Redbench_synthetic"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

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

for BMAX in 100 500 1000 1500 2000; do
    RESULT_DIR="time_dependent_output/ex4/result_b${BMAX}"
    mkdir -p ${RESULT_DIR}

    echo ""
    echo "========================================================================"
    echo "B_max = ${BMAX} MB"
    echo "========================================================================"

    # ------------------------------------------------------------------
    restart_container
    echo ""
    echo "------------------------------------------------------------------------"
    echo "[B_max=${BMAX}] Dynamic (pruning あり)"
    echo "開始時刻: $(date)"
    echo "------------------------------------------------------------------------"
    python ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase post-opt \
      --query-set Redbench_synthetic \
      --optimization-mode dynamic \
      --exp-suffix ${SUFFIX} \
      --use-pruning \
      --pruning-parallel \
      --noise-ratio 0.0 \
      --b-max ${BMAX} \
      --recalc \
      --use-docker \
      --ease
    echo "完了時刻: $(date)"

    # ------------------------------------------------------------------
    restart_container
    echo ""
    echo "------------------------------------------------------------------------"
    echo "[B_max=${BMAX}] Static (average, utility)"
    echo "開始時刻: $(date)"
    echo "------------------------------------------------------------------------"
    python ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase post-opt \
      --query-set Redbench_synthetic \
      --optimization-mode static \
      --static-timestep average \
      --static-algorithm utility \
      --exp-suffix ${SUFFIX} \
      --noise-ratio 0.0 \
      --b-max ${BMAX} \
      --recalc \
      --use-docker \
      --ease
    echo "完了時刻: $(date)"

    # ------------------------------------------------------------------
    restart_container
    echo ""
    echo "------------------------------------------------------------------------"
    echo "[B_max=${BMAX}] Adaptive (w=4)"
    echo "開始時刻: $(date)"
    echo "------------------------------------------------------------------------"
    python ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase post-opt \
      --query-set Redbench_synthetic \
      --optimization-mode adaptive \
      --window-size 4 \
      --freq-weight linear \
      --exp-suffix ${SUFFIX} \
      --noise-ratio 0.0 \
      --b-max ${BMAX} \
      --recalc \
      --use-docker \
      --ease
    echo "完了時刻: $(date)"

    # ------------------------------------------------------------------
    echo ""
    echo ">>> B_max=${BMAX} の結果を ${RESULT_DIR} に移動中..."
    mv -f ${BASE_DIR}/td_mv_optimization_result${SUFFIX}.json        ${RESULT_DIR}/ 2>/dev/null || true
    mv -f ${BASE_DIR}/static_mv_optimization_result${SUFFIX}.json    ${RESULT_DIR}/ 2>/dev/null || true
    mv -f ${BASE_DIR}/adaptive_mv_optimization_result_w4${SUFFIX}.json ${RESULT_DIR}/ 2>/dev/null || true
    mv -f ${BASE_DIR}/benchmark_results_dynamic${SUFFIX}.json        ${RESULT_DIR}/ 2>/dev/null || true
    mv -f ${BASE_DIR}/benchmark_results_static${SUFFIX}.json         ${RESULT_DIR}/ 2>/dev/null || true
    mv -f ${BASE_DIR}/benchmark_results_adaptive_w4${SUFFIX}.json    ${RESULT_DIR}/ 2>/dev/null || true
    echo ">>> 移動完了: ${RESULT_DIR}"

done

echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "結果:"
for BMAX in 100 500 1000 1500 2000; do
    echo "  time_dependent_output/ex4/result_b${BMAX}/"
done
echo "========================================================================"
