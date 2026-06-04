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
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_2_10 \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_2_10_wo.txt
rename_to_wo _16_2_10
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_2_10] Dynamic (pruning あり)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_2_10 \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_2_10.txt
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
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_mono \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_mono_wo.txt
rename_to_wo _16_mono
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "[_16_mono] Dynamic (pruning あり)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_mono \
  --use-pruning \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_mono.txt
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
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_peak \
  --noise-ratio 0.0 \
  --b-max 100 \
  --recalc \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_dynamic_16_peak_wo.txt
rename_to_wo _16_peak
echo "完了時刻: $(date)"

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


# ======================================================================
# 結果を result_100M_edbt/ に集約
# ======================================================================

echo ""
echo "========================================================================"
echo "結果を ${RESULT_DIR} に移動中..."
echo "========================================================================"

mv -f ${BASE_DIR}/td_mv_optimization_result_16_*.json        ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/static_mv_optimization_result_16_*.json    ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/adaptive_mv_optimization_result_w4_16_*.json ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/benchmark_results_dynamic_16_*.json         ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/benchmark_results_static_16_*.json          ${RESULT_DIR}/ 2>/dev/null || true
mv -f ${BASE_DIR}/benchmark_results_adaptive_w4_16_*.json     ${RESULT_DIR}/ 2>/dev/null || true

echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "結果: ${RESULT_DIR}"
echo "========================================================================"
