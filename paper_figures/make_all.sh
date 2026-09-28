#!/bin/bash
# ======================================================================
# Generates all figures and tables of the paper (input: time_dependent_output/rq*/ from paper/*.sh).
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
    setup_frequency_patterns.py        # Fig.5
    setup_redbench_total_count.py      # Fig.6
    rq1_exp1_1_timestep_time.py        # Fig.7
    rq1_exp1_2_timestep_scaling.py     # Fig.8
    rq1_exp1_3_query_scaling.py        # Fig.9
    rq2_prediction_recall.py           # Fig.10
    rq3_pruning.py                     # Table 2
    rq4_capacity.py                    # Fig.11
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
