#!/bin/bash
# ======================================================================
# RQ4 / Experiment 4: storage constraint vs. total execution time
#
#   job-ceb-2, Cycles / Evolution and Stagnation / Growth and Spikes
#   B_max = 500, 1000, 1500, 2000 MB, methods = Proposed / Static / Adapt
#     b500        : same setting as RQ1 Exp1-1 -> its results are copied
#                   (the paper also uses the same files; if the RQ1 results are
#                   missing or REUSE=0, it is run)
#     b1000 and up: Proposed uses parallel pruning (as in the original runs)
#   The y-axis is summary.total_benchmark_time (Static includes the initial MV build).
#
# Output: time_dependent_output/rq4/{24_2_10,24_mono,24_peak}/b{500,1000,1500,2000}/
# Original paper data: time_dependent_output/ex4_ok_{cycle,mono,peak}/b*/
#
# Usage: bash paper_scripts/rq4_capacity.sh
#        SUFFIXES="_24_peak" CAPS="1000 2000" bash paper_scripts/rq4_capacity.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
read -r -a CAPS <<< "${CAPS:-500 1000 1500 2000}"
SRC_RQ1="${TD}/rq1/exp1_1/job-ceb-2"

log "==== RQ4: capacity ${CAPS[*]} MB x (${SUFFIXES[*]}) ===="
backup_intermediates job-ceb-2

for SFX in "${SUFFIXES[@]}"; do
    for CAP in "${CAPS[@]}"; do
        DEST="${TD}/rq4/${SFX#_}/b${CAP}"
        log "---- ${SFX} / B_max=${CAP}MB ----"

        if [ "${CAP}" = "${B_MAX}" ]; then
            # Same setting as RQ1 (sequential pruning)
            METHODS=(dynamic_seq static adaptive)
        else
            METHODS=(dynamic_par static adaptive)
        fi

        for M in "${METHODS[@]}"; do
            read -r OPT BENCH <<< "$(result_files "${M}" "${SFX}")"
            if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
                log "SKIP (result exists): ${DEST}/${BENCH}"
                continue
            fi
            if [ "${CAP}" = "${B_MAX}" ] && reuse_copy "${SRC_RQ1}" "${DEST}" "${OPT}" "${BENCH}"; then
                continue
            fi
            run_postopt job-ceb-2 "${SFX}" "${M}" "${CAP}" "${DEST}"
        done
    done
done

log "==== RQ4 done: ${TD}/rq4/ ===="
