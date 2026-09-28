#!/bin/bash
# ======================================================================
# RQ3 / Experiment 3（Table 2）: 候補プルーニングの有無の比較
#
#   job-ceb-2, Cycles / Evolution and Stagnation / Growth and Spikes, B_max = 500MB
#     With pruning   : RQ1 Exp1-1 の Proposed と同一条件 → その結果をコピー（論文でも同一ファイル）
#                      （RQ1 の結果が無い、または REUSE=0 なら逐次プルーニングで実行）
#     Without pruning: プルーニングなしで post-opt を実行し、ファイル名に _wo を付ける
#   表の列: 候補数 = pruning_info, 最適化時間 = pruning_time_sec + solve_time_sec,
#           総実行時間 = summary.total_benchmark_time, 目的関数値 = -objective / 1000
#
# 出力: time_dependent_output/rq3/
#   td_mv_optimization_result_{fq}{,_wo}.json, benchmark_results_dynamic_{fq}{,_wo}.json, log/
# 論文の元データ: time_dependent_output/ex3_500M_ok/
#
# 使い方: bash paper/rq3_pruning.sh
#         SUFFIXES="_24_mono" bash paper/rq3_pruning.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
DEST="${TD}/rq3"
SRC_RQ1="${TD}/rq1/exp1_1/job-ceb-2"

log "==== RQ3: プルーニング有無 (${SUFFIXES[*]}) ===="
backup_intermediates job-ceb-2

for SFX in "${SUFFIXES[@]}"; do
    # With pruning
    read -r OPT BENCH <<< "$(result_files dynamic_seq "${SFX}")"
    if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
        log "SKIP（結果あり）: ${DEST}/${BENCH}"
    elif ! reuse_copy "${SRC_RQ1}" "${DEST}" "${OPT}" "${BENCH}"; then
        run_postopt job-ceb-2 "${SFX}" dynamic_seq "${B_MAX}" "${DEST}"
    fi

    # Without pruning
    run_postopt job-ceb-2 "${SFX}" dynamic_nopr "${B_MAX}" "${DEST}" _wo
done

log "==== RQ3 完了: ${DEST}/ ===="
