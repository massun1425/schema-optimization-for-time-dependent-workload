#!/bin/bash
# ======================================================================
# Preprocessing: Phases 1-5 + cost recalculation (produces the inputs of all RQs)
#
#   From the SQL files in 01_queries/<set>/ this generates
#     02_json/<set>/*.json                           (Phase 1: EXPLAIN, needs the DB)
#     03_parsed/<set>/qp_class.pkl, parse_summary    (Phase 2: parsing)
#     node IDs added to 02_json/<set>/*.json         (Phase 3)
#     04_migration/<set>/simple_migration_plans.json (Phase 4)
#     04_migration/<set>/simple_migration_costs.json (Phase 5: sampling, needs the DB;
#                                                     overwritten by the recalculation)
#
# By default, query sets whose output (simple_migration_costs.json) already
# exists are skipped. With FORCE_PREP=1 the existing 02_json/03_parsed/04_migration
# directories are moved to <dir>/<set>__backup_<timestamp>/ (never deleted) and
# regenerated.
#
# Sampling rates follow the original preprocessing scripts (scripts/shell/run_ex0_*.sh):
#   job-ceb-2 = high, Redbench_synthetic = low
#
# Usage: bash paper/00_prepare.sh
#        SETS="job-ceb-2" bash paper/00_prepare.sh
#        DRY_RUN=1 bash paper/00_prepare.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SETS <<< "${SETS:-job-ceb-2 Redbench_synthetic}"
FORCE_PREP="${FORCE_PREP:-0}"
LOG_DIR="${TD}/prep/log"

wait_for_postgres() {
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] wait for ${CONTAINER}"
        return 0
    fi
    until docker exec "${CONTAINER}" pg_isready -U postgres > /dev/null 2>&1; do
        sleep 2
    done
}

sampling_args() {
    case $1 in
        job-ceb-2) echo "--use-sampling --sampling-rate high" ;;
        *)         echo "--use-sampling" ;;
    esac
}

for SET in "${SETS[@]}"; do
    log "==== Preprocessing: ${SET} ===="
    [ -d "01_queries/${SET}" ] || die "01_queries/${SET} not found"

    if [ -f "04_migration/${SET}/simple_migration_costs.json" ]; then
        if [ "${FORCE_PREP}" != "1" ]; then
            log "SKIP: 04_migration/${SET}/simple_migration_costs.json already exists (use FORCE_PREP=1 to regenerate)"
            continue
        fi
        TS_NOW=$(date +%Y%m%d_%H%M%S)
        for D in 02_json 03_parsed 04_migration; do
            if [ -d "${D}/${SET}" ]; then
                log "Backing up: ${D}/${SET} -> ${D}/${SET}__backup_${TS_NOW}"
                run mv "${D}/${SET}" "${D}/${SET}__backup_${TS_NOW}"
            fi
        done
    fi

    wait_for_postgres
    run_main "${LOG_DIR}/${SET}_phase1.log" - --phase 1 --query-set "${SET}" --use-docker || die "Phase 1 failed (${SET})"
    run_main "${LOG_DIR}/${SET}_phase2.log" - --phase 2 --query-set "${SET}"               || die "Phase 2 failed (${SET})"
    run_main "${LOG_DIR}/${SET}_phase3.log" - --phase 3 --query-set "${SET}"               || die "Phase 3 failed (${SET})"
    run_main "${LOG_DIR}/${SET}_phase4.log" - --phase 4 --query-set "${SET}"               || die "Phase 4 failed (${SET})"
    read -r -a SARGS <<< "$(sampling_args "${SET}")"
    run_main "${LOG_DIR}/${SET}_phase5.log" - --phase 5 --query-set "${SET}" "${SARGS[@]}" --use-docker || die "Phase 5 failed (${SET})"

    # Phase 5.5: recalculate the costs using the node structure in the pickle and
    # overwrite the cost file (all experiments use it via --recalc)
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] ${PY} scripts/recalculate_costs.py --query-set ${SET} --overwrite"
    else
        mkdir -p "${LOG_DIR}"
        "${PY}" scripts/recalculate_costs.py --query-set "${SET}" --overwrite 2>&1 \
            | tee -a "${LOG_DIR}/${SET}_recalc.log" || die "recalculate_costs failed (${SET})"
    fi
    log "Done: ${SET}"
done
