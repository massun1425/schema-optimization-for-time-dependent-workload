#!/bin/bash

# タイムステップ数比較実験スクリプト（peak パターン）
# タイムステップ数（8, 16, 24, 32）を変えた頻度ファイルを用いて
# Dynamic(pruning有), Static(average, utility), Adaptive(w=4) を実行し
# 結果を time_dependent_output/ex1_peak/cycles/ に集約する
#
# 使い方: bash scripts/shell/ex1_peak_cycle.sh
#         nohup bash scripts/shell/ex1_peak_cycle.sh > ex1_peak_cycle.log 2>&1 &

set -e

SCRIPT_DIR="scripts"
OUTPUT_DIR="time_dependent_output/ex1_2/peak/log"
RESULT_DIR="time_dependent_output/ex1_2/peak"
BASE_DIR="time_dependent_output/job"

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

# ======================================================================
# _8_peak
# ======================================================================

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_8_peak] Dynamic (pruning あり)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _8_peak \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_8_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_8_peak] Static (average)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --exp-suffix _8_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_8_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_8_peak] Adaptive (w=4)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode adaptive \
  --window-size 4 \
  --exp-suffix _8_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_w4_8_peak.txt
echo "完了時刻: $(date)"

# ======================================================================
# _16_peak
# ======================================================================

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_peak] Dynamic (pruning あり)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_peak \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_peak] Static (average)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --exp-suffix _16_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_16_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_peak] Adaptive (w=4)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode adaptive \
  --window-size 4 \
  --exp-suffix _16_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_w4_16_peak.txt
echo "完了時刻: $(date)"

# ======================================================================
# _24_peak
# ======================================================================

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_24_peak] Dynamic (pruning あり)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _24_peak \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_24_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_24_peak] Static (average)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --exp-suffix _24_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_24_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_24_peak] Adaptive (w=4)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode adaptive \
  --window-size 4 \
  --exp-suffix _24_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_w4_24_peak.txt
echo "完了時刻: $(date)"

# ======================================================================
# _32_peak
# ======================================================================

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_32_peak] Dynamic (pruning あり)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _32_peak \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_32_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_32_peak] Static (average)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm utility \
  --exp-suffix _32_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_static_32_peak.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_32_peak] Adaptive (w=4)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode adaptive \
  --window-size 4 \
  --exp-suffix _32_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_w4_32_peak.txt
echo "完了時刻: $(date)"

# ======================================================================
# 結果を cycles/ に集約
# ======================================================================

echo ""
echo "========================================================================"
echo "結果を ${RESULT_DIR} に移動中..."
echo "========================================================================"

mv -f ${BASE_DIR}/td_mv_optimization_result_*.json        ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/static_mv_optimization_result_*.json    ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/adaptive_mv_optimization_result_*.json  ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/benchmark_results_dynamic_*.json        ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/benchmark_results_static_*.json         ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/benchmark_results_adaptive_*.json       ${RESULT_DIR}/ 2>/dev/null || true

echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "結果: ${RESULT_DIR}"
echo "========================================================================"
