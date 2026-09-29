#!/bin/bash
# ======================================================================
# Rebuild cluster_55_53_combined (the base of 01_queries/Redbench_synthetic) from the
# Redbench workloads of clusters 53 and 55. See README.md in this directory.
#
#   1) workload.csv -> query set with 2-hour time steps (_2h), for each cluster
#   2) frequencies x2 (_2h -> _2h_x2)
#   3) combine the two clusters by summing the frequencies (_2h and _2h_x2)
#
# The outputs are byte-identical to the original query sets (the combined set: identical
# SQL files and frequencies). Existing output directories are never overwritten; set
# OUT_ROOT to build somewhere else, e.g.
#   OUT_ROOT=/tmp/rebuild bash scripts/redbench_synthesizer/build_cluster_53_55_combined.sh
#
# Environment variables (defaults in parentheses):
#   PY        Python interpreter (.venv/bin/python if present, else python3)
#   RB_WL     Redbench workload directory (Redbench/output/generated_workloads/imdb/serverless)
#   C53_DIR   cluster 53 workload (${RB_WL}/cluster_53/database_1/050312-050511)
#   C55_DIR   cluster 55 workload (${RB_WL}/cluster_55/database_0/0525-0526)
#   OUT_ROOT  parent directory of the output query sets (01_queries)
# ======================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${ROOT}"
HERE="scripts/redbench_synthesizer"

if [ -z "${PY:-}" ]; then
    if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
fi
RB_WL="${RB_WL:-Redbench/output/generated_workloads/imdb/serverless}"
C53_DIR="${C53_DIR:-${RB_WL}/cluster_53/database_1/050312-050511}"
C55_DIR="${C55_DIR:-${RB_WL}/cluster_55/database_0/0525-0526}"
OUT_ROOT="${OUT_ROOT:-01_queries}"

SET53="${OUT_ROOT}/cluster_53_join"
SET55="${OUT_ROOT}/cluster_55_join"
SETC="${OUT_ROOT}/cluster_55_53_combined"

die() { echo "ERROR: $*" >&2; exit 1; }

for f in "${C53_DIR}/workload.csv" "${C53_DIR}/queries.json" "${C55_DIR}/workload.csv" "${C55_DIR}/queries.json"; do
    [ -f "${f}" ] || die "${f} not found (generate it with Redbench; see README.md)"
done
for d in "${SET53}" "${SET55}" "${SETC}"; do
    [ -e "${d}" ] && die "${d} already exists (not overwritten; set OUT_ROOT to build elsewhere)"
done

# 1) workload.csv -> query set (2-hour time steps, 48 hours = 24 steps)
#    --queries-json-path names the files after the matched JOB/CEB queries;
#    --sanitize-ceb rewrites the CEB-style queries to SELECT COUNT(*)
gen() {  # <workload dir> <output dir> <start> <end>
    "${PY}" "${HERE}/generate_queryset_from_workload_csv.py" \
        --csv-path "$1/workload.csv" --queries-json-path "$1/queries.json" \
        --output-query-dir "$2" --start "$3" --end "$4" \
        --step-hours 2 --freq-suffix _2h --sanitize-ceb
}
gen "${C53_DIR}" "${SET53}" 2024-05-03T12:00:00 2024-05-05T11:59:59
gen "${C55_DIR}" "${SET55}" 2024-05-25T00:00:00 2024-05-26T23:59:59

# 2) frequencies x2
for d in "${SET53}" "${SET55}"; do
    "${PY}" "${HERE}/scale_frequency.py" \
        --input "${d}/frequency_time_dependent_2h.json" \
        --output "${d}/frequency_time_dependent_2h_x2.json" \
        --factor 2 --description-suffix " (doubled frequencies)"
done

# 3) combine the clusters (sum of the frequencies of the same time step)
for SFX in _2h _2h_x2; do
    "${PY}" "${HERE}/merge_query_folders_sum.py" \
        --dir1 "${SET53}" --dir2 "${SET55}" --out "${SETC}" \
        --freq-name "frequency_time_dependent${SFX}.json" \
        --description "Generated from workload.csv (cluster 53 and 55 combined)"
done

echo "Done: ${SETC} ($(ls "${SETC}"/*.sql | wc -l) queries)"
