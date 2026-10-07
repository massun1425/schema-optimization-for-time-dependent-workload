#!/bin/bash
# ======================================================================
# Runs all experiments of the paper in order.
#   RQ2 / RQ3 Exp3-1 / RQ4 reuse the results of RQ1 Exp1-1, so Exp1-1 runs first.
#   Every script skips runs whose results already exist, so re-running this
#   script resumes after an interruption.
#
# Usage: nohup bash paper_scripts/run_all.sh > paper_run_all.log 2>&1 &
#        DRY_RUN=1 bash paper_scripts/run_all.sh     # only print the commands
# ======================================================================
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

STEPS=(
    00_prepare.sh                    # preprocessing (skipped if the inputs exist)
    rq1_exp1_1_timestep_time.sh      # RQ1 Exp1-1
    rq3_exp3_1_pruning.sh            # RQ3 Exp3-1
    rq4_capacity.sh                  # RQ4
    rq2_prediction_recall.sh         # RQ2
    rq3_exp3_2_timestep_scaling.sh   # RQ3 Exp3-2 (Phase 6 only)
    rq3_exp3_3_query_scaling.sh      # RQ3 Exp3-3 (Phase 6 only, long-running)
)

for S in "${STEPS[@]}"; do
    echo "######## $(date '+%F %T') START ${S}"
    bash "${HERE}/${S}" || { echo "######## FAILED: ${S}"; exit 1; }
    echo "######## $(date '+%F %T') END   ${S}"
done
