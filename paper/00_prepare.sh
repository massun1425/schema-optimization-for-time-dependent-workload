#!/bin/bash
# ======================================================================
# 前処理: Phase 1〜5 + コスト再計算（全 RQ の入力を作る）
#
#   01_queries/<set>/ の SQL から
#     02_json/<set>/*.json                          (Phase 1: EXPLAIN, 要DB)
#     03_parsed/<set>/qp_class.pkl, parse_summary   (Phase 2: parse)
#     02_json/<set>/*.json にノードID付与           (Phase 3)
#     04_migration/<set>/simple_migration_plans.json (Phase 4)
#     04_migration/<set>/simple_migration_costs.json (Phase 5: sampling, 要DB → recalc で上書き)
#   を生成する。
#
# 既定では、出力（simple_migration_costs.json）が既にあるクエリセットはスキップする。
# FORCE_PREP=1 のときは、既存の 02_json/03_parsed/04_migration を
# <dir>/<set>__backup_<日時>/ へ退避してから再生成する（削除はしない）。
#
# サンプリング率は元の前処理スクリプト（scripts/shell/run_ex0_*.sh）に合わせる:
#   job-ceb-2 = high, Redbench_synthetic = low
#
# 使い方: bash paper/00_prepare.sh
#         SETS="job-ceb-2" bash paper/00_prepare.sh
#         DRY_RUN=1 bash paper/00_prepare.sh
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
    log "==== 前処理: ${SET} ===="
    [ -d "01_queries/${SET}" ] || die "01_queries/${SET} がありません"

    if [ -f "04_migration/${SET}/simple_migration_costs.json" ]; then
        if [ "${FORCE_PREP}" != "1" ]; then
            log "SKIP: 04_migration/${SET}/simple_migration_costs.json が既にあります（再生成は FORCE_PREP=1）"
            continue
        fi
        TS_NOW=$(date +%Y%m%d_%H%M%S)
        for D in 02_json 03_parsed 04_migration; do
            if [ -d "${D}/${SET}" ]; then
                log "退避: ${D}/${SET} -> ${D}/${SET}__backup_${TS_NOW}"
                run mv "${D}/${SET}" "${D}/${SET}__backup_${TS_NOW}"
            fi
        done
    fi

    wait_for_postgres
    run_main "${LOG_DIR}/${SET}_phase1.log" - --phase 1 --query-set "${SET}" --use-docker || die "Phase 1 失敗 (${SET})"
    run_main "${LOG_DIR}/${SET}_phase2.log" - --phase 2 --query-set "${SET}"               || die "Phase 2 失敗 (${SET})"
    run_main "${LOG_DIR}/${SET}_phase3.log" - --phase 3 --query-set "${SET}"               || die "Phase 3 失敗 (${SET})"
    run_main "${LOG_DIR}/${SET}_phase4.log" - --phase 4 --query-set "${SET}"               || die "Phase 4 失敗 (${SET})"
    read -r -a SARGS <<< "$(sampling_args "${SET}")"
    run_main "${LOG_DIR}/${SET}_phase5.log" - --phase 5 --query-set "${SET}" "${SARGS[@]}" --use-docker || die "Phase 5 失敗 (${SET})"

    # Phase 5.5: pickle のノード構造でコストを再計算して上書き（全実験は --recalc でこれを使う）
    if [ "${DRY_RUN}" = "1" ]; then
        echo "  [dry-run] ${PY} scripts/recalculate_costs.py --query-set ${SET} --overwrite"
    else
        mkdir -p "${LOG_DIR}"
        "${PY}" scripts/recalculate_costs.py --query-set "${SET}" --overwrite 2>&1 \
            | tee -a "${LOG_DIR}/${SET}_recalc.log" || die "recalculate_costs 失敗 (${SET})"
    fi
    log "完了: ${SET}"
done
