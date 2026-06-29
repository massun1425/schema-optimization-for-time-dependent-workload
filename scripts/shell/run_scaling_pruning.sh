#!/bin/bash
# ======================================================================
# スケーラビリティ検証: pruning付き dynamic 最適化（最適化のみ・ベンチマークなし）
#
# 合成クエリセット job-ceb-2-q{10000,20000,40000} に対して、CF Pruning +
# 時間依存型(dynamic)最適化を実行し、プルーニング時間・ILP求解時間・総実行
# 時間を計測する。DB実行は行わない（最適化フェーズ6のみ）。
#
# 事前準備（未生成の場合のみ。一度だけ）:
#   .venv/bin/python scripts/extract_sparse_base.py --query-set job-ceb-2
#   for N in 10000 20000 40000; do
#     .venv/bin/python scripts/generate_synthetic_scaling.py \
#         --base-set job-ceb-2 --queries $N --freq-suffix _24_mono
#   done
#
# 使い方:
#   bash scripts/shell/run_scaling_pruning.sh
#   nohup bash scripts/shell/run_scaling_pruning.sh > run_scaling_pruning.log 2>&1 &
# ======================================================================
set -u

# リポジトリルートへ移動（このスクリプトは scripts/shell/ にあるので2階層上）
cd "$(dirname "$0")/../.."

PY="${PY:-.venv/bin/python}"      # PY 環境変数で上書き可
SCRIPT_DIR="scripts"
FREQ_SUFFIX="_24_mono"            # 既存頻度パターンを流用
B_MAX=500                         # ストレージ予算 (MB)
QUERY_COUNTS=(60000 80000 100000)  # 検証するクエリ数
FORCE="${FORCE:-0}"               # FORCE=1 で結果済みも再実行

OUT_DIR="progress/scaling_pruning"
mkdir -p "${OUT_DIR}"
SUMMARY="${OUT_DIR}/summary.txt"
echo "======================================================================" | tee "${SUMMARY}"
echo "スケーラビリティ実験(pruning+dynamic) 開始: $(date)"                    | tee -a "${SUMMARY}"
echo "freq=${FREQ_SUFFIX}  B_max=${B_MAX}MB  python=${PY}"                    | tee -a "${SUMMARY}"
echo "======================================================================" | tee -a "${SUMMARY}"

for N in "${QUERY_COUNTS[@]}"; do
    SET="job-ceb-2-q${N}"
    LOG="${OUT_DIR}/q${N}.log"

    if [ ! -f "03_parsed/${SET}/qp_class.pkl" ]; then
        echo "[${N}] SKIP: 03_parsed/${SET}/qp_class.pkl が見つかりません（先に生成してください）" | tee -a "${SUMMARY}"
        continue
    fi

    # bigsubs(static) の結果ファイルで結果済み判定する（dynamic とは別ファイル）
    # RESULT_JSON="time_dependent_output/${SET}/static_bigsubs_optimization_result${FREQ_SUFFIX}.json"
    # if [ "${FORCE}" != "1" ] && [ -f "${RESULT_JSON}" ]; then
    #     echo "[${N}] SKIP: 結果済み (${RESULT_JSON})。再実行するには FORCE=1" | tee -a "${SUMMARY}"
    #     continue
    # fi

    echo "" | tee -a "${SUMMARY}"
    echo "----------------------------------------------------------------------" | tee -a "${SUMMARY}"
    echo "[${N} queries] set=${SET}  開始: $(date)" | tee -a "${SUMMARY}"
    echo "----------------------------------------------------------------------"

    # 標準出力にも表示しつつログにも保存（PYTHONUNBUFFERED=1 でリアルタイム出力）
    PYTHONUNBUFFERED=1 ${PY} ${SCRIPT_DIR}/run_experiment_normal.py \
        --phase 6 \
        --query-set "${SET}" \
        --optimization-mode dynamic \
        --use-pruning \
        --pruning-parallel \
        --pruning-workers 16 \
        --exp-suffix "${FREQ_SUFFIX}" \
        --b-max "${B_MAX}" \
        --recalc \
        2>&1 | tee "${LOG}"

    STATUS=${PIPESTATUS[0]}
    echo "[${N}] 終了: $(date)  (exit=${STATUS}, log=${LOG})" | tee -a "${SUMMARY}"
    if [ ${STATUS} -ne 0 ]; then
        echo "[${N}] ERROR: 異常終了。ログ末尾:" | tee -a "${SUMMARY}"
        tail -5 "${LOG}" | sed "s/^/[${N}]   /" | tee -a "${SUMMARY}"
        continue
    fi

    # 主要な計測値を要約に抽出
    grep -iE "Promising MVs|Reduction|候補をフィルタリング|プルーニング完了|ILP求解時間|フェーズ総実行時間" "${LOG}" \
        | sed "s/^/[${N}] /" | tee -a "${SUMMARY}"
done

echo "" | tee -a "${SUMMARY}"
echo "======================================================================" | tee -a "${SUMMARY}"
echo "全実験完了: $(date)" | tee -a "${SUMMARY}"
echo "要約: ${SUMMARY}" | tee -a "${SUMMARY}"
echo "======================================================================" | tee -a "${SUMMARY}"
