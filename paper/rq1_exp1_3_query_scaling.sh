#!/bin/bash
# ======================================================================
# RQ1 / Experiment 1-3（Fig.9）: 最適化時間 vs クエリ数
#
#   job-ceb-2 をブロック複製した合成クエリセット job-ceb-2-q{N}
#   N = 20k, 40k, 60k, 80k, 100k, T = 24（_24_mono）, B_max = 500MB
#   Phase 6（最適化）のみ実行する。DB は不要。
#     Static          : static_mv_optimization_result_24_mono.json   （縦軸 = execution_time）
#     Proposed (w/)   : td_mv_optimization_result_24_mono_wp.json     （縦軸 = phase_time_sec, 並列16）
#     Proposed (w/o)  : td_mv_optimization_result_24_mono_wo.json     （縦軸 = phase_time_sec, ${TIMEOUT}打ち切り）
#   プルーニングなしがタイムアウトしたら、それより大きい N は打ち切って DNF とする。
#
# 合成クエリセット（03_parsed/04_migration/01_queries の job-ceb-2-q{N}）は、
# 既にあればそのまま使う（論文の結果と同一の入力を保つため、再生成はしない）。
# 無い場合のみ scripts/generate_synthetic_scaling.py（seed=0）で生成する。
#
# 出力: time_dependent_output/rq1/exp1_3/job-ceb-2-q{N}/
# 論文の元データ: time_dependent_output/job-ceb-2-q{N}/
#   （旧名: プルーニングなし = td_mv_optimization_result_24_mono.json。新構成では _wo を付ける）
#
# 使い方: bash paper/rq1_exp1_3_query_scaling.sh
#         QUERY_COUNTS="20000 40000" bash paper/rq1_exp1_3_query_scaling.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a QUERY_COUNTS <<< "${QUERY_COUNTS:-20000 40000 60000 80000 100000}"
SFX="_24_mono"
DEST_BASE="${TD}/rq1/exp1_3"

# 0) 合成クエリセットの用意（無い場合のみ生成）
if [ ! -f "03_parsed/job-ceb-2/sparse_base.pkl" ]; then
    log "sparse_base.pkl を生成"
    run "${PY}" scripts/extract_sparse_base.py --query-set job-ceb-2 || die "extract_sparse_base 失敗"
fi
for N in "${QUERY_COUNTS[@]}"; do
    if [ -f "03_parsed/job-ceb-2-q${N}/qp_class.pkl" ]; then
        log "既存の合成クエリセットを使用: job-ceb-2-q${N}"
    else
        log "合成クエリセットを生成: job-ceb-2-q${N}"
        run "${PY}" scripts/generate_synthetic_scaling.py \
            --base-set job-ceb-2 --queries "${N}" --freq-suffix "${SFX}" \
            || die "generate_synthetic_scaling 失敗 (N=${N})"
    fi
done

# 1) Static と Proposed（プルーニングあり）
for N in "${QUERY_COUNTS[@]}"; do
    SET="job-ceb-2-q${N}"
    DEST="${DEST_BASE}/${SET}"
    log "==== RQ1 Exp1-3: ${SET} (Static / w/ pruning) ===="
    run_phase6 "${SET}" "${SFX}" static        "${B_MAX}" "${DEST}" "" || die "Static 失敗 (N=${N})"
    run_phase6 "${SET}" "${SFX}" dynamic_par16 "${B_MAX}" "${DEST}" _wp || die "w/ pruning 失敗 (N=${N})"
done

# 2) Proposed（プルーニングなし）: タイムアウトした時点で打ち切り
DNF=0
for N in "${QUERY_COUNTS[@]}"; do
    SET="job-ceb-2-q${N}"
    DEST="${DEST_BASE}/${SET}"
    if [ ${DNF} -eq 1 ]; then
        log "SKIP（より小さい N で DNF）: ${SET}"
        write_note "${DEST}/DNF${SFX}_wo.txt" "DNF: skipped because a smaller N timed out"
        continue
    fi
    log "==== RQ1 Exp1-3: ${SET} (w/o pruning, timeout ${TIMEOUT}) ===="
    run_phase6 "${SET}" "${SFX}" dynamic_nopr "${B_MAX}" "${DEST}" _wo "${TIMEOUT}"
    STATUS=$?
    if [ ${STATUS} -eq 124 ]; then
        log "TIMEOUT (> ${TIMEOUT}): ${SET} → DNF"
        write_note "${DEST}/DNF${SFX}_wo.txt" "DNF: timeout ${TIMEOUT} ($(date '+%F %T'))"
        DNF=1
    elif [ ${STATUS} -ne 0 ]; then
        die "w/o pruning 失敗 (N=${N}, exit=${STATUS})"
    fi
done

log "==== RQ1 Exp1-3 完了: ${DEST_BASE}/ ===="
