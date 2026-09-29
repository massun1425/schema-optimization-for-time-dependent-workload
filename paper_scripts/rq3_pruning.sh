#!/bin/bash
# ======================================================================
# RQ3 / Experiment 3 (Table 2): with vs. without candidate pruning
#
#   job-ceb-2, Cycles / Evolution and Stagnation / Growth and Spikes, B_max = 500MB
#     With pruning   : same setting as Proposed in RQ1 Exp1-1 -> its results are copied
#                      (the paper also uses the same files; if the RQ1 results are
#                      missing or REUSE=0, it is run with sequential pruning)
#     Without pruning: post-opt without pruning; _wo is appended to the file names
#   Table columns: #candidates = pruning_info,
#                  optimization time = pruning_time_sec + solve_time_sec,
#                  total execution time = summary.total_benchmark_time,
#                  objective value = -objective / 1000
#
# Output: time_dependent_output/rq3/
#   td_mv_optimization_result_{fq}{,_wo}.json, benchmark_results_dynamic_{fq}{,_wo}.json, log/
# Original paper data: time_dependent_output/ex3_500M_ok/
#
# Usage: bash paper_scripts/rq3_pruning.sh
#        SUFFIXES="_24_mono" bash paper_scripts/rq3_pruning.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
DEST="${TD}/rq3"
SRC_RQ1="${TD}/rq1/exp1_1/job-ceb-2"

log "==== RQ3: with vs. without pruning (${SUFFIXES[*]}) ===="
backup_intermediates job-ceb-2

for SFX in "${SUFFIXES[@]}"; do
    # With pruning
    read -r OPT BENCH <<< "$(result_files dynamic_seq "${SFX}")"
    if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
        log "SKIP (result exists): ${DEST}/${BENCH}"
    elif ! reuse_copy "${SRC_RQ1}" "${DEST}" "${OPT}" "${BENCH}"; then
        run_postopt job-ceb-2 "${SFX}" dynamic_seq "${B_MAX}" "${DEST}"
    fi

    # Without pruning
    run_postopt job-ceb-2 "${SFX}" dynamic_nopr "${B_MAX}" "${DEST}" _wo
done

log "==== RQ3 done: ${DEST}/ ===="
