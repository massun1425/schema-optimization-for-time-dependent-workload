#!/bin/bash
# ======================================================================
# Generates all figures and tables of the paper (input: time_dependent_output/rq*/ from paper_scripts/*.sh).
# Output: paper_figures/output/
#
# Usage: bash paper_figures/make_all.sh
#        bash paper_figures/make_all.sh --td-dir <dir> --out-dir <dir>   # passed to every script
# Figures whose inputs are incomplete are not skipped but reported as errors (missing files are listed).
# ======================================================================
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "${HERE}/.." || exit 1
PY="${PY:-.venv/bin/python}"

SCRIPTS=(
    setup_frequency_patterns.py        # workload setup
    setup_redbench_total_count.py      # workload setup
    rq1_exp1_1_timestep_time.py        # RQ1 Exp1-1
    rq3_exp3_2_timestep_scaling.py     # RQ3 Exp3-2
    rq3_exp3_3_query_scaling.py        # RQ3 Exp3-3
    rq2_prediction_recall.py           # RQ2
    rq3_exp3_1_pruning.py              # RQ3 Exp3-1
    rq4_capacity.py                    # RQ4
)

FAILED=()
for S in "${SCRIPTS[@]}"; do
    echo "== ${S}"
    PYTHONDONTWRITEBYTECODE=1 "${PY}" "${HERE}/${S}" "$@" || FAILED+=("${S}")
done

if [ ${#FAILED[@]} -gt 0 ]; then
    echo "Failed: ${FAILED[*]}"
    exit 1
fi
echo "Done"
