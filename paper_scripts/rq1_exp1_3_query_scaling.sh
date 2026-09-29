#!/bin/bash
# ======================================================================
# RQ1 / Experiment 1-3 (Fig. 9): optimization time vs. number of queries
#
#   Synthetic query sets job-ceb-2-q{N} obtained by block-replicating job-ceb-2
#   N = 20k, 40k, 60k, 80k, 100k, T = 24 (_24_mono), B_max = 500MB
#   Only the optimization (Phase 6) is run; no DB is needed.
#     Static          : static_mv_optimization_result_24_mono.json  (y-axis = execution_time)
#     Proposed (w/)   : td_mv_optimization_result_24_mono_wp.json    (y-axis = phase_time_sec, 16 parallel workers)
#     Proposed (w/o)  : td_mv_optimization_result_24_mono_wo.json    (y-axis = phase_time_sec, stopped after ${TIMEOUT})
#   If a run without pruning times out, larger N are skipped and marked as DNF.
#
# Existing synthetic query sets (job-ceb-2-q{N} in 03_parsed/04_migration/01_queries)
# are used as they are (they are not regenerated, so that the input stays identical
# to the paper). Missing ones are generated with scripts/generate_synthetic_scaling.py (seed=0).
#
# Output: time_dependent_output/rq1/exp1_3/job-ceb-2-q{N}/
# Original paper data: time_dependent_output/job-ceb-2-q{N}/
#   (old name for w/o pruning: td_mv_optimization_result_24_mono.json; the new layout adds _wo)
#
# Usage: bash paper_scripts/rq1_exp1_3_query_scaling.sh
#        QUERY_COUNTS="20000 40000" bash paper_scripts/rq1_exp1_3_query_scaling.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a QUERY_COUNTS <<< "${QUERY_COUNTS:-20000 40000 60000 80000 100000}"
SFX="_24_mono"
DEST_BASE="${TD}/rq1/exp1_3"

# 0) Prepare the synthetic query sets (generated only if missing)
if [ ! -f "03_parsed/job-ceb-2/sparse_base.pkl" ]; then
    log "Generating sparse_base.pkl"
    run "${PY}" scripts/extract_sparse_base.py --query-set job-ceb-2 || die "extract_sparse_base failed"
fi
for N in "${QUERY_COUNTS[@]}"; do
    if [ -f "03_parsed/job-ceb-2-q${N}/qp_class.pkl" ]; then
        log "Using the existing synthetic query set: job-ceb-2-q${N}"
    else
        log "Generating the synthetic query set: job-ceb-2-q${N}"
        run "${PY}" scripts/generate_synthetic_scaling.py \
            --base-set job-ceb-2 --queries "${N}" --freq-suffix "${SFX}" \
            || die "generate_synthetic_scaling failed (N=${N})"
    fi
done

# 1) Static and Proposed (with pruning)
for N in "${QUERY_COUNTS[@]}"; do
    SET="job-ceb-2-q${N}"
    DEST="${DEST_BASE}/${SET}"
    log "==== RQ1 Exp1-3: ${SET} (Static / w/ pruning) ===="
    run_phase6 "${SET}" "${SFX}" static        "${B_MAX}" "${DEST}" "" || die "Static failed (N=${N})"
    run_phase6 "${SET}" "${SFX}" dynamic_par16 "${B_MAX}" "${DEST}" _wp || die "w/ pruning failed (N=${N})"
done

# 2) Proposed (without pruning): stop at the first timeout
DNF=0
for N in "${QUERY_COUNTS[@]}"; do
    SET="job-ceb-2-q${N}"
    DEST="${DEST_BASE}/${SET}"
    if [ ${DNF} -eq 1 ]; then
        log "SKIP (DNF at a smaller N): ${SET}"
        write_note "${DEST}/DNF${SFX}_wo.txt" "DNF: skipped because a smaller N timed out"
        continue
    fi
    log "==== RQ1 Exp1-3: ${SET} (w/o pruning, timeout ${TIMEOUT}) ===="
    run_phase6 "${SET}" "${SFX}" dynamic_nopr "${B_MAX}" "${DEST}" _wo "${TIMEOUT}"
    STATUS=$?
    if [ ${STATUS} -eq 124 ]; then
        log "TIMEOUT (> ${TIMEOUT}): ${SET} -> DNF"
        write_note "${DEST}/DNF${SFX}_wo.txt" "DNF: timeout ${TIMEOUT} ($(date '+%F %T'))"
        DNF=1
    elif [ ${STATUS} -ne 0 ]; then
        die "w/o pruning failed (N=${N}, exit=${STATUS})"
    fi
done

log "==== RQ1 Exp1-3 done: ${DEST_BASE}/ ===="
