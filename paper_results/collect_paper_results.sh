#!/bin/bash
# ======================================================================
# Collects the results reported in the paper into paper_results/ (tracked by git),
# using the same layout as the output of the paper/ scripts (time_dependent_output/rq*/),
# so that paper_figures/ can regenerate the figures and tables with
#     bash paper_figures/make_all.sh --td-dir paper_results
#
# The sources are the original result directories under time_dependent_output/
# (e.g. job-ceb-2/result_500M_ok/, ex2_500M_ok/, ex3_500M_ok/, ex4_ok_*/), which exist
# only in the original experiment environment.
#
# Safety: files are only copied (cp -p); nothing is moved or deleted. An existing
# destination file is skipped if it is identical to the source and the script stops
# if it differs (nothing is overwritten).
#
# The figures and tables in paper_results/figures/ are generated from the collected files with
#     bash paper_figures/make_all.sh --td-dir paper_results --out-dir paper_results/figures
#
# Usage: bash paper_results/collect_paper_results.sh
# ======================================================================
set -u -o pipefail

# This script lives in paper_results/; run everything from the repository root
cd "$(dirname "$0")/.." || exit 1

SRC="time_dependent_output"
DST="paper_results"
COPIED=0
SKIPPED=0

log() { echo "[$(date '+%F %T')] $*"; }
die() { log "ERROR: $*"; exit 1; }

# copy_file <source> <destination>
copy_file() {
    local src=$1 dst=$2
    [ -f "${src}" ] || die "Source not found: ${src}"
    if [ -e "${dst}" ]; then
        if cmp -s "${src}" "${dst}"; then
            SKIPPED=$((SKIPPED + 1))
            return 0
        fi
        die "Destination exists and differs (not overwritten): ${dst}"
    fi
    mkdir -p "$(dirname "${dst}")"
    cp -p "${src}" "${dst}" || die "cp failed: ${src} -> ${dst}"
    cmp -s "${src}" "${dst}" || die "Copy verification failed: ${dst}"
    COPIED=$((COPIED + 1))
}

# write_note <destination> <text> : creates a marker file (never overwrites a different one)
write_note() {
    local dst=$1 text=$2
    if [ -e "${dst}" ]; then
        [ "$(cat "${dst}")" = "${text}" ] && { SKIPPED=$((SKIPPED + 1)); return 0; }
        die "Destination exists and differs (not overwritten): ${dst}"
    fi
    mkdir -p "$(dirname "${dst}")"
    echo "${text}" > "${dst}"
    COPIED=$((COPIED + 1))
}

# ---------------------------------------------------------------------
# RQ1 Exp1-1 (Fig. 7): job-ceb-2, 3 patterns x 3 methods
# ---------------------------------------------------------------------
for FQ in 24_2_10 24_mono 24_peak; do
    S="${SRC}/job-ceb-2/result_500M_ok"
    D="${DST}/rq1/exp1_1/job-ceb-2"
    for F in "benchmark_results_dynamic_${FQ}.json" "benchmark_results_static_${FQ}.json" \
             "benchmark_results_adaptive_w4_${FQ}.json" "td_mv_optimization_result_${FQ}.json" \
             "static_mv_optimization_result_${FQ}.json" "adaptive_mv_optimization_result_w4_${FQ}.json"; do
        copy_file "${S}/${F}" "${D}/${F}"
    done
done

# RQ1 Exp1-1 (Fig. 7): Redbench synthetic (no noise)
S="${SRC}/ex2_500M_ok"
D="${DST}/rq1/exp1_1/Redbench_synthetic"
for F in benchmark_results_dynamic_2h_x2_50x.json benchmark_results_static_2h_x2_50x.json \
         benchmark_results_adaptive_w4_2h_x2_50x.json td_mv_optimization_result_2h_x2_50x.json \
         static_mv_optimization_result_2h_x2_50x.json adaptive_mv_optimization_result_w4_2h_x2_50x.json; do
    copy_file "${S}/${F}" "${D}/${F}"
done

# ---------------------------------------------------------------------
# RQ1 Exp1-2 (Fig. 8): number of time steps, with (_wp) / without (_wo) pruning
# ---------------------------------------------------------------------
for T in 12 18 24 30 36 42; do
    for TAG in wp wo; do
        F="td_mv_optimization_result_${T}_mono_${TAG}.json"
        copy_file "${SRC}/job-ceb-2/result_scaling_time_ok/${F}" "${DST}/rq1/exp1_2/${F}"
    done
done

# ---------------------------------------------------------------------
# RQ1 Exp1-3 (Fig. 9): number of queries
#   The original run stored the result without pruning as td_mv_optimization_result_24_mono.json;
#   it is renamed to *_wo.json as written by paper/rq1_exp1_3_query_scaling.sh.
# ---------------------------------------------------------------------
for N in 20000 40000 60000 80000 100000; do
    S="${SRC}/job-ceb-2-q${N}"
    D="${DST}/rq1/exp1_3/job-ceb-2-q${N}"
    copy_file "${S}/static_mv_optimization_result_24_mono.json" "${D}/static_mv_optimization_result_24_mono.json"
    copy_file "${S}/td_mv_optimization_result_24_mono_wp.json" "${D}/td_mv_optimization_result_24_mono_wp.json"
    if [ -f "${S}/td_mv_optimization_result_24_mono.json" ]; then
        copy_file "${S}/td_mv_optimization_result_24_mono.json" "${D}/td_mv_optimization_result_24_mono_wo.json"
    fi
done
write_note "${DST}/rq1/exp1_3/job-ceb-2-q60000/DNF_24_mono_wo.txt" \
    "DNF: timeout 24h (original run: Gurobi was still solving after 82,276 s)"
write_note "${DST}/rq1/exp1_3/job-ceb-2-q80000/DNF_24_mono_wo.txt" \
    "DNF: skipped because a smaller N timed out"
write_note "${DST}/rq1/exp1_3/job-ceb-2-q100000/DNF_24_mono_wo.txt" \
    "DNF: skipped because a smaller N timed out"

# ---------------------------------------------------------------------
# RQ2 (Fig. 10): prediction recall (all result files of ex2_500M_ok)
# ---------------------------------------------------------------------
for F in "${SRC}"/ex2_500M_ok/*.json; do
    copy_file "${F}" "${DST}/rq2/$(basename "${F}")"
done

# ---------------------------------------------------------------------
# RQ3 (Table 2): with / without pruning
# ---------------------------------------------------------------------
for F in "${SRC}"/ex3_500M_ok/*.json; do
    copy_file "${F}" "${DST}/rq3/$(basename "${F}")"
done

# ---------------------------------------------------------------------
# RQ4 (Fig. 11): storage constraint
# ---------------------------------------------------------------------
for P in cycle:24_2_10 mono:24_mono peak:24_peak; do
    for B in 500 1000 1500 2000; do
        for F in "${SRC}/ex4_ok_${P%%:*}/b${B}"/*.json; do
            copy_file "${F}" "${DST}/rq4/${P#*:}/b${B}/$(basename "${F}")"
        done
    done
done

# ---------------------------------------------------------------------
# Checksums of the collected result files (excluding README.md, this list, this script
# and the generated figures in figures/)
# ---------------------------------------------------------------------
(cd "${DST}" && find . -type f ! -name SHA256SUMS ! -name README.md ! -name collect_paper_results.sh \
    ! -path './figures/*' | sort | sed 's|^\./||' \
    | xargs sha256sum > SHA256SUMS)

log "Done: ${COPIED} files created, ${SKIPPED} identical files skipped -> ${DST}/"
