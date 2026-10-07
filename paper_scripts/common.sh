#!/bin/bash
# ======================================================================
# Shared settings and helpers for the paper experiment scripts
# (sourced by every paper_scripts/*.sh).
#
# run_experiment_normal.py writes its results with fixed file names directly
# under time_dependent_output/<query_set>/ ("staging"). After every run these
# scripts move the results into time_dependent_output/rq*/... . Existing files
# in staging with the same name are moved aside only while a run is in
# progress and are put back afterwards (protect_file / restore_file).
#
# Environment variables:
#   DRY_RUN=1   print the commands without running anything (no file operations at all)
#   FORCE=1     re-run even if the result already exists (default: skip -> resumable)
#   REUSE=0     do not copy results of identical runs from another RQ; run them again
#               (default: 1 = reuse)
#   PY          python executable (default: .venv/bin/python)
#   CONTAINER   PostgreSQL container name (default: mv_postgres)
#   TIMEOUT     time limit for optimization without pruning (default: 24h)
# ======================================================================

set -u -o pipefail

PAPER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${PAPER_DIR}/.." && pwd)"
cd "${REPO_ROOT}" || exit 1

PY="${PY:-.venv/bin/python}"
CONTAINER="${CONTAINER:-mv_postgres}"
DRY_RUN="${DRY_RUN:-0}"
FORCE="${FORCE:-0}"
REUSE="${REUSE:-1}"
TIMEOUT="${TIMEOUT:-24h}"

TD="time_dependent_output"
MAIN="scripts/run_experiment_normal.py"
B_MAX=500   # default storage constraint in the paper (MB)

log() { echo "[$(date '+%F %T')] $*"; }
die() { log "ERROR: $*"; exit 1; }

# Every operation that modifies files goes through run (only printed when DRY_RUN=1)
run() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] $*"
        return 0
    fi
    "$@"
}

# run_main <logfile> <timeout|-> <args...>
#   Runs run_experiment_normal.py and also saves its output to the log file.
#   Returns the exit code of python (of timeout if a limit is given; 124 = timed out).
run_main() {
    local logfile=$1 to=$2
    shift 2
    if [ "${DRY_RUN}" = "1" ]; then
        if [ "${to}" = "-" ]; then
            echo "  [dry-run] ${PY} ${MAIN} $*"
        else
            echo "  [dry-run] timeout ${to} ${PY} ${MAIN} $*"
        fi
        return 0
    fi
    mkdir -p "$(dirname "${logfile}")"
    if [ "${to}" = "-" ]; then
        env PYTHONUNBUFFERED=1 "${PY}" "${MAIN}" "$@" 2>&1 | tee -a "${logfile}"
    else
        timeout "${to}" env PYTHONUNBUFFERED=1 "${PY}" "${MAIN}" "$@" 2>&1 | tee -a "${logfile}"
    fi
    return "${PIPESTATUS[0]}"
}

# Restart PostgreSQL before each benchmark to clear the caches
restart_container() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] docker restart ${CONTAINER}"
        return 0
    fi
    log "Restarting PostgreSQL container: ${CONTAINER}"
    docker restart "${CONTAINER}" > /dev/null || die "docker restart failed"
    sleep 15
    until docker exec "${CONTAINER}" pg_isready -U postgres > /dev/null 2>&1; do
        sleep 2
    done
}

# ----------------------------------------------------------------------
# Protection of existing files in staging (time_dependent_output/<set>/)
#
# 1) Result JSONs: right before a run, only the existing files whose names
#    collide with the files about to be written are moved to
#    <set>/_stash/in_use/; they are put back once the results have been
#    collected into rq*/. On errors or interruption the EXIT trap puts them
#    back as well (only if the original location is free).
#    -> Existing results (e.g. the Exp3-3 source data in job-ceb-2-q{N}/)
#       stay where they are.
# 2) Intermediates (timestep_*.sql, static_*initial_mvs.sql, jobs/): Phases 7/8
#    delete and regenerate them, so the post-opt scripts move them once to
#    <set>/_stash/intermediates_<timestamp>/ on their first run (afterwards they
#    were produced by these scripts and may be overwritten; marker: .paper_staging).
# ----------------------------------------------------------------------

# protect_file <query_set> <file_name>
protect_file() {
    local src="${TD}/$1/$2"
    local stash="${TD}/$1/_stash/in_use"
    [ -e "${src}" ] || return 0
    if [ -e "${stash}/$2" ]; then
        die "A file with the same name is already stashed (left over from an interrupted run): ${stash}/$2 — please check it manually"
    fi
    log "Stashing: ${src} -> ${stash}/"
    run mkdir -p "${stash}"
    run mv "${src}" "${stash}/$2"
}

# restore_file <query_set> <file_name>
restore_file() {
    local dst="${TD}/$1/$2"
    local stashed="${TD}/$1/_stash/in_use/$2"
    [ -e "${stashed}" ] || return 0
    if [ -e "${dst}" ]; then
        log "WARNING: cannot restore ${stashed} because ${dst} exists (please check it manually)"
        return 0
    fi
    log "Restoring: ${stashed} -> ${dst}"
    run mv "${stashed}" "${dst}"
}

# On EXIT, put back any files that are still stashed
restore_all() {
    local f set name
    shopt -s nullglob
    for f in "${TD}"/*/_stash/in_use/*; do
        set=$(basename "$(dirname "$(dirname "$(dirname "${f}")")")")
        name=$(basename "${f}")
        restore_file "${set}" "${name}"
    done
    shopt -u nullglob
}
[ "${DRY_RUN}" = "1" ] || trap restore_all EXIT

# backup_intermediates <query_set> : one-time backup of intermediates
# (called at the beginning of the post-opt scripts)
backup_intermediates() {
    local dir="${TD}/$1"
    [ -f "${dir}/.paper_staging" ] && return 0
    local stash
    stash="${dir}/_stash/intermediates_$(date +%Y%m%d_%H%M%S)"
    local -a files=()
    shopt -s nullglob
    files+=("${dir}"/timestep_*.sql)
    files+=("${dir}"/static_*initial_mvs.sql)
    shopt -u nullglob
    [ -d "${dir}/jobs" ] && files+=("${dir}/jobs")
    if [ ${#files[@]} -gt 0 ]; then
        log "Backing up intermediates: ${#files[@]} items under ${dir} -> ${stash}/"
        run mkdir -p "${stash}"
        run mv "${files[@]}" "${stash}/"
    fi
    run mkdir -p "${dir}"
    run touch "${dir}/.paper_staging"
}

# is_done <file>... : returns 0 if all files exist (always 1 when FORCE=1)
is_done() {
    [ "${FORCE}" = "1" ] && return 1
    local f
    for f in "$@"; do
        [ -f "${f}" ] || return 1
    done
    return 0
}

# collect <query_set> <dest_dir> <file name in staging> [destination file name]
collect() {
    local src="${TD}/$1/$3"
    local dst="$2/${4:-$3}"
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] mv ${src} ${dst}"
        return 0
    fi
    [ -f "${src}" ] || die "Result file not found: ${src}"
    mkdir -p "$2"
    mv -f "${src}" "${dst}"
    log "  -> ${dst}"
}

# reuse_copy <src_dir> <dest_dir> <file>...
#   Copies the results of an identical run from another RQ (the paper data also
#   shares the same files). Returns 1 if REUSE=0 or the files are not all present
#   in src (the caller then falls back to running the experiment).
reuse_copy() {
    local src=$1 dest=$2
    shift 2
    [ "${REUSE}" = "1" ] || return 1
    local f
    for f in "$@"; do
        [ -f "${src}/${f}" ] || return 1
    done
    log "Reusing: ${src} -> ${dest} ($*)"
    run mkdir -p "${dest}"
    for f in "$@"; do
        if [ -f "${dest}/${f}" ] && [ "${FORCE}" != "1" ]; then
            continue
        fi
        run cp -p "${src}/${f}" "${dest}/${f}"
    done
    return 0
}

# write_note <file> <text> : writes a marker file such as a DNF note
write_note() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] write '$2' > $1"
        return 0
    fi
    mkdir -p "$(dirname "$1")"
    echo "$2" > "$1"
}

# ----------------------------------------------------------------------
# Method definitions (arguments checked against the result JSONs of the paper)
#   dynamic_seq   : Proposed (sequential pruning)                ... RQ1 Exp1-1 / RQ4 b500
#   dynamic_par   : Proposed (parallel pruning)                  ... RQ3 Exp3-1 / RQ3 Exp3-2 / RQ4 b1000-2000
#   dynamic_par16 : Proposed (parallel pruning, 16 workers)      ... RQ3 Exp3-3
#   dynamic_nopr  : Proposed (without pruning)                   ... RQ3 Exp3-1 / RQ3 Exp3-2 / RQ3 Exp3-3
#   static        : Static (UtilityOptimizerV2, average over all time steps)
#   adaptive      : Adapt (window size 4, linear recency weights)
#   adaptive_w<N> : Adapt with window size N (e.g. adaptive_w8)
# ----------------------------------------------------------------------
method_args() {
    case $1 in
        dynamic_seq)   echo "--optimization-mode dynamic --use-pruning" ;;
        dynamic_par)   echo "--optimization-mode dynamic --use-pruning --pruning-parallel" ;;
        dynamic_par16) echo "--optimization-mode dynamic --use-pruning --pruning-parallel --pruning-workers 16" ;;
        dynamic_nopr)  echo "--optimization-mode dynamic" ;;
        static)        echo "--optimization-mode static --static-timestep average --static-algorithm utility" ;;
        adaptive)      echo "--optimization-mode adaptive --window-size 4 --freq-weight linear" ;;
        adaptive_w[0-9]*) echo "--optimization-mode adaptive --window-size ${1#adaptive_w} --freq-weight linear" ;;
        *) die "Unknown method: $1" ;;
    esac
}

# result_files <method> <suffix> : "optimization-result benchmark-result" file names in staging
result_files() {
    case $1 in
        dynamic*) echo "td_mv_optimization_result$2.json benchmark_results_dynamic$2.json" ;;
        static)   echo "static_mv_optimization_result$2.json benchmark_results_static$2.json" ;;
        adaptive) echo "adaptive_mv_optimization_result_w4$2.json benchmark_results_adaptive_w4$2.json" ;;
        adaptive_w[0-9]*) echo "adaptive_mv_optimization_result_w${1#adaptive_w}$2.json benchmark_results_adaptive_w${1#adaptive_w}$2.json" ;;
        *) die "Unknown method: $1" ;;
    esac
}

# run_postopt <query_set> <suffix> <method> <b_max> <dest_dir> [tag]
#   Runs Phases 6-9 (optimization -> MV SQL -> query rewriting -> benchmark (--ease))
#   and moves the optimization and benchmark results into dest_dir.
#   tag is appended to the file names (e.g. _wo).
run_postopt() {
    local set=$1 sfx=$2 method=$3 bmax=$4 dest=$5 tag=${6:-}
    local opt bench
    read -r opt bench <<< "$(result_files "${method}" "${sfx}")"
    local opt_dst="${opt%.json}${tag}.json"
    local bench_dst="${bench%.json}${tag}.json"

    if is_done "${dest}/${opt_dst}" "${dest}/${bench_dst}"; then
        log "SKIP (result exists): ${dest}/${bench_dst}"
        return 0
    fi

    local -a margs
    read -r -a margs <<< "$(method_args "${method}")"
    log "RUN post-opt: set=${set} suffix=${sfx} method=${method} B_max=${bmax}MB ${tag:+tag=${tag}}"
    protect_file "${set}" "${opt}"
    protect_file "${set}" "${bench}"
    restart_container
    run_main "${dest}/log/${method}${sfx}${tag}.log" - \
        --phase post-opt \
        --query-set "${set}" \
        --exp-suffix "${sfx}" \
        "${margs[@]}" \
        --noise-ratio 0.0 \
        --b-max "${bmax}" \
        --recalc \
        --use-docker \
        --ease \
        || die "post-opt failed: set=${set} suffix=${sfx} method=${method}"
    collect "${set}" "${dest}" "${opt}" "${opt_dst}"
    collect "${set}" "${dest}" "${bench}" "${bench_dst}"
    restore_file "${set}" "${opt}"
    restore_file "${set}" "${bench}"
}

# run_phase6 <query_set> <suffix> <method> <b_max> <dest_dir> <tag> [timeout|-]
#   Runs only the optimization (Phase 6; no DB needed) and moves the
#   optimization result into dest_dir.
#   Returns: 0 = success or skipped, 124 = timed out, other = failure
run_phase6() {
    local set=$1 sfx=$2 method=$3 bmax=$4 dest=$5 tag=$6 to=${7:--}
    local opt _bench
    read -r opt _bench <<< "$(result_files "${method}" "${sfx}")"
    local opt_dst="${opt%.json}${tag}.json"

    if is_done "${dest}/${opt_dst}"; then
        log "SKIP (result exists): ${dest}/${opt_dst}"
        return 0
    fi

    local -a margs
    read -r -a margs <<< "$(method_args "${method}")"
    log "RUN phase6: set=${set} suffix=${sfx} method=${method} B_max=${bmax}MB tag=${tag} timeout=${to}"
    protect_file "${set}" "${opt}"
    run_main "${dest}/log/phase6_${method}${sfx}${tag}.log" "${to}" \
        --phase 6 \
        --query-set "${set}" \
        --exp-suffix "${sfx}" \
        "${margs[@]}" \
        --b-max "${bmax}" \
        --recalc
    local status=$?
    if [ ${status} -ne 0 ]; then
        # If no partial output was written (e.g. timeout), put the original back
        # (otherwise the EXIT trap prints a warning)
        restore_file "${set}" "${opt}"
        return ${status}
    fi
    collect "${set}" "${dest}" "${opt}" "${opt_dst}"
    restore_file "${set}" "${opt}"
}
