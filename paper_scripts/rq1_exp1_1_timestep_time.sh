#!/bin/bash
# ======================================================================
# RQ1 / Experiment 1-1: execution time per time step (Proposed / Adapt / Static)
#
#   job-ceb-2         : Cycles (_24_2_10) / Evolution and Stagnation (_24_mono) / Growth and Spikes (_24_peak)
#   Redbench_synthetic: _2h_x2_50x
#   B_max = 500MB, T = 24, --recalc --ease
#
# Output:
#   time_dependent_output/rq1/exp1_1/job-ceb-2/
#   time_dependent_output/rq1/exp1_1/Redbench_synthetic/
#     {td_mv,static_mv,adaptive_mv}_optimization_result*.json
#     benchmark_results_{dynamic,static,adaptive_w4}*.json
#     log/
#
# These results are reused by RQ2 (recall 100%), RQ3 Exp3-1 (with pruning) and RQ4 (b500).
# Original paper data: time_dependent_output/job-ceb-2/result_500M_ok/, ex2_500M_ok/
#
# Usage: bash paper_scripts/rq1_exp1_1_timestep_time.sh
#        SUFFIXES="_24_mono" SKIP_REDBENCH=1 bash paper_scripts/rq1_exp1_1_timestep_time.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
METHODS=(dynamic_seq static adaptive)
SKIP_REDBENCH="${SKIP_REDBENCH:-0}"

DEST_JOB="${TD}/rq1/exp1_1/job-ceb-2"
DEST_RB="${TD}/rq1/exp1_1/Redbench_synthetic"
RB_SUFFIX="_2h_x2_50x"

log "==== RQ1 Exp1-1: job-ceb-2 (${SUFFIXES[*]}) ===="
backup_intermediates job-ceb-2
for SFX in "${SUFFIXES[@]}"; do
    for M in "${METHODS[@]}"; do
        run_postopt job-ceb-2 "${SFX}" "${M}" "${B_MAX}" "${DEST_JOB}"
    done
done

if [ "${SKIP_REDBENCH}" != "1" ]; then
    log "==== RQ1 Exp1-1: Redbench_synthetic (${RB_SUFFIX}) ===="
    backup_intermediates Redbench_synthetic
    for M in "${METHODS[@]}"; do
        run_postopt Redbench_synthetic "${RB_SUFFIX}" "${M}" "${B_MAX}" "${DEST_RB}"
    done
fi

log "==== RQ1 Exp1-1 done: ${TD}/rq1/exp1_1/ ===="
