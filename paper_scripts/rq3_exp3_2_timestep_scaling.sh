#!/bin/bash
# ======================================================================
# RQ3 / Experiment 3-2: optimization time vs. number of time steps
#
#   job-ceb-2 (2,515 queries, 26,312 candidates), Evolution and Stagnation (_{T}_mono)
#   T = 12, 18, 24, 30, 36, 42, B_max = 500MB
#   Only the optimization (Phase 6) is run; no DB is needed.
#     _wp: Proposed (parallel pruning)
#     _wo: Proposed (without pruning; each run is stopped after ${TIMEOUT})
#   The y-axis is phase_time_sec in the result JSON.
#
# If a run without pruning times out, larger T are skipped
# (DNF_{T}_mono_wo.txt is written).
#
# Output: time_dependent_output/rq3/exp3_2/td_mv_optimization_result_{T}_mono_{wp,wo}.json
# Original paper data: time_dependent_output/job-ceb-2/result_scaling_time_ok/
#
# Usage: bash paper_scripts/rq3_exp3_2_timestep_scaling.sh
#        TIMESTEPS="12 18" bash paper_scripts/rq3_exp3_2_timestep_scaling.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a TIMESTEPS <<< "${TIMESTEPS:-12 18 24 30 36 42}"
DEST="${TD}/rq3/exp3_2"

log "==== RQ3 Exp3-2: number of time steps ${TIMESTEPS[*]} ===="

# Pass 1: with pruning (all T)
for T in "${TIMESTEPS[@]}"; do
    run_phase6 job-ceb-2 "_${T}_mono" dynamic_par "${B_MAX}" "${DEST}" _wp \
        || die "optimization with pruning failed (T=${T})"
done

# Pass 2: without pruning (stop at the first timeout)
for T in "${TIMESTEPS[@]}"; do
    run_phase6 job-ceb-2 "_${T}_mono" dynamic_nopr "${B_MAX}" "${DEST}" _wo "${TIMEOUT}"
    STATUS=$?
    if [ ${STATUS} -eq 124 ]; then
        log "TIMEOUT (> ${TIMEOUT}): T=${T} -> DNF; skipping larger T"
        write_note "${DEST}/DNF_${T}_mono_wo.txt" "DNF: timeout ${TIMEOUT} ($(date '+%F %T'))"
        break
    elif [ ${STATUS} -ne 0 ]; then
        die "optimization without pruning failed (T=${T}, exit=${STATUS})"
    fi
done

log "==== RQ3 Exp3-2 done: ${DEST}/ ===="
