#!/bin/bash
# ======================================================================
# Additional experiment: window size of the Adapt baseline
#
#   Query set: job (the 113 JOB queries), patterns _24_2_10 (Cycles), _24_mono (Evolution
#   and Stagnation), _24_peak (Growth and Spikes), Adapt with window sizes 2, 4, 8
#   (k = 1, 3, 7 in the notation of the paper; the paper uses 4), B_max = 500MB.
#   The settings are those of the paper except the query set and the window size.
#
#   1) Preprocessing of job (Phases 1-5.5, needs the DB) with paper_scripts/00_prepare.sh.
#      Existing 02_json/job, 03_parsed/job and 04_migration/job directories are moved to
#      <dir>/job__backup_<timestamp>/ (never deleted). The preprocessing is skipped when
#      04_migration/job/simple_migration_costs.meta.json shows that it has been done with
#      the high-rate sampler and the cost recalculation.
#   2) For every pattern and window size: Phases 6-9 for Adapt only (optimization, MV SQL,
#      query rewriting, benchmark with --ease), as in the other experiments.
#
# Output: time_dependent_output/extra/adapt_window/job/
#           adaptive_mv_optimization_result_w{W}_{suffix}.json
#           benchmark_results_adaptive_w{W}_{suffix}.json
#         The total execution time of every run is printed at the end.
#
# Usage: bash paper_scripts/extra_adapt_window_size.sh
#        WINDOWS="2 8" SUFFIXES="_24_mono" bash paper_scripts/extra_adapt_window_size.sh
#        BMAX_MB=200 bash paper_scripts/extra_adapt_window_size.sh   # other storage constraint
#        DRY_RUN=1 bash paper_scripts/extra_adapt_window_size.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

SET="job"
read -r -a WINDOWS <<< "${WINDOWS:-2 4 8}"
read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
B_MAX="${BMAX_MB:-${B_MAX}}"
DEST="${TD}/extra/adapt_window/${SET}"
META="04_migration/${SET}/simple_migration_costs.meta.json"

# 1) Preprocessing (done once)
prep_done() {
    [ -f "${META}" ] || return 1
    "${PY}" - "${META}" <<'EOF'
import json, sys
meta = json.load(open(sys.argv[1]))
ok = meta.get("cost_estimation", {}).get("sampling_rate") == "high" and "cost_recalculation" in meta
sys.exit(0 if ok else 1)
EOF
}
if prep_done; then
    log "SKIP preprocessing: ${META} shows that ${SET} has been preprocessed"
else
    log "==== Preprocessing: ${SET} (existing outputs are moved to backups) ===="
    SETS="${SET}" FORCE_PREP=1 bash "${PAPER_DIR}/00_prepare.sh" || die "preprocessing failed (${SET})"
fi

# 2) Adapt with every window size (Phases 6-9)
backup_intermediates "${SET}"
for SFX in "${SUFFIXES[@]}"; do
    for W in "${WINDOWS[@]}"; do
        log "==== Adapt window size ${W}: ${SET} ${SFX} (B_max = ${B_MAX}MB) ===="
        run_postopt "${SET}" "${SFX}" "adaptive_w${W}" "${B_MAX}" "${DEST}"
    done
done

# 3) Summary: total execution time (s) of every run
[ "${DRY_RUN}" = "1" ] && exit 0
log "Total execution time (s) [summary.total_benchmark_time]"
"${PY}" - "${DEST}" "${SUFFIXES[*]}" "${WINDOWS[*]}" <<'EOF'
import json, sys
from pathlib import Path
dest, suffixes, windows = Path(sys.argv[1]), sys.argv[2].split(), sys.argv[3].split()
print("pattern".ljust(12) + "".join(f"w={w}".rjust(14) for w in windows))
for sfx in suffixes:
    row = []
    for w in windows:
        f = dest / f"benchmark_results_adaptive_w{w}{sfx}.json"
        row.append(f"{json.load(open(f))['summary']['total_benchmark_time']:.1f}" if f.exists() else "-")
    print(sfx.ljust(12) + "".join(v.rjust(14) for v in row))
EOF
