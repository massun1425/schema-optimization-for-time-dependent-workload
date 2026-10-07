#!/bin/bash
# ======================================================================
# RQ3 / Experiment 3-1: with vs. without candidate pruning
#
#   job-ceb-2, Cycles / Evolution and Stagnation / Growth and Spikes, B_max = 500MB
#     With pruning   : the optimization (Phase 6) is run with parallel pruning, the method
#                      of Exp3-2 (dynamic_par). Its result is identical to that of Proposed in
#                      RQ1 Exp1-1 (sequential pruning) except for the timing, so the benchmark
#                      result of RQ1 Exp1-1 is copied. If it is missing or REUSE=0, post-opt is
#                      run with parallel pruning.
#     Without pruning: post-opt without pruning; _wo is appended to the file names
#   Table columns: #candidates = pruning_info,
#                  optimization time = phase_time_sec (the whole Phase 6, as in Exp3-2 and Exp3-3),
#                  total execution time = summary.total_benchmark_time,
#                  objective value = -objective / 1000
#
# Output: time_dependent_output/rq3/exp3_1/
#   td_mv_optimization_result_{fq}{,_wo}.json, benchmark_results_dynamic_{fq}{,_wo}.json, log/
# Original paper data: time_dependent_output/ex3_500M_ok/
#
# Usage: bash paper_scripts/rq3_exp3_1_pruning.sh
#        SUFFIXES="_24_mono" bash paper_scripts/rq3_exp3_1_pruning.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
DEST="${TD}/rq3/exp3_1"
SRC_RQ1="${TD}/rq1/exp1_1/job-ceb-2"

log "==== RQ3 Exp3-1: with vs. without pruning (${SUFFIXES[*]}) ===="
backup_intermediates job-ceb-2

for SFX in "${SUFFIXES[@]}"; do
    # With pruning: benchmark of RQ1 Exp1-1 + optimization with parallel pruning
    read -r OPT BENCH <<< "$(result_files dynamic_par "${SFX}")"
    if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
        log "SKIP (result exists): ${DEST}/${BENCH}"
    elif reuse_copy "${SRC_RQ1}" "${DEST}" "${BENCH}"; then
        run_phase6 job-ceb-2 "${SFX}" dynamic_par "${B_MAX}" "${DEST}" "" \
            || die "Phase 6 with parallel pruning failed (${SFX})"
    else
        run_postopt job-ceb-2 "${SFX}" dynamic_par "${B_MAX}" "${DEST}"
    fi

    # Without pruning
    run_postopt job-ceb-2 "${SFX}" dynamic_nopr "${B_MAX}" "${DEST}" _wo
done

log "==== RQ3 Exp3-1 done: ${DEST}/ ===="
