#!/bin/bash
# ======================================================================
# RQ2 / Experiment 2: robustness against workload prediction recall
#
#   Redbench_synthetic (_2h_x2_50x), B_max = 500MB
#   recall = 100 - noise (%), noise = 5, 10, ..., 50%
#   Each query execution is replaced by the original query (not using MVs) with
#   probability noise (--noise-ratio, --ease).
#   The optimization is not repeated: Phases 7-9 are run with the optimization
#   result of recall 100%.
#   Adapt does not use predictions, so it is unaffected by noise and only the
#   recall-100% result is needed.
#
# Steps:
#   1) recall 100%: copy the Redbench results of RQ1 Exp1-1 (the paper also uses
#      the same files). If the RQ1 results are missing or REUSE=0, run post-opt here.
#   2) For Proposed and Static, place the optimization result in staging,
#      regenerate Phase 7 (MV SQL) and Phase 8 (query rewriting), and run
#      Phase 9 for each noise level.
#
# Output: time_dependent_output/rq2/
#   benchmark_results_{dynamic,static}_2h_x2_50x{,_noise5,...,_noise50}.json
#   benchmark_results_adaptive_w4_2h_x2_50x.json, the optimization results, log/
# Original paper data: time_dependent_output/ex2_500M_ok/
#
# Usage: bash paper_scripts/rq2_prediction_recall.sh
#        NOISE_PCTS="5 10" bash paper_scripts/rq2_prediction_recall.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

SET="Redbench_synthetic"
SFX="_2h_x2_50x"
DEST="${TD}/rq2"
SRC_RQ1="${TD}/rq1/exp1_1/${SET}"
read -r -a NOISE_PCTS <<< "${NOISE_PCTS:-5 10 15 20 25 30 35 40 45 50}"

log "==== RQ2: ${SET} (${SFX}), noise = ${NOISE_PCTS[*]} % ===="
backup_intermediates "${SET}"

# 1) recall 100% (noise 0)
for M in dynamic_seq static adaptive; do
    read -r OPT BENCH <<< "$(result_files "${M}" "${SFX}")"
    if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
        log "SKIP (result exists): ${DEST}/${BENCH}"
    elif ! reuse_copy "${SRC_RQ1}" "${DEST}" "${OPT}" "${BENCH}"; then
        run_postopt "${SET}" "${SFX}" "${M}" "${B_MAX}" "${DEST}"
    fi
done

# 2) noise > 0: regenerate Phases 7/8 from the optimization result and run Phase 9 per noise level
for MODE in dynamic static; do
    if [ "${MODE}" = "dynamic" ]; then
        read -r OPT _ <<< "$(result_files dynamic "${SFX}")"
    else
        read -r OPT _ <<< "$(result_files static "${SFX}")"
    fi

    # Only the noise levels that have not been run yet
    TODO=()
    for P in "${NOISE_PCTS[@]}"; do
        is_done "${DEST}/benchmark_results_${MODE}${SFX}_noise${P}.json" || TODO+=("${P}")
    done
    if [ ${#TODO[@]} -eq 0 ]; then
        log "SKIP (results exist for all noise levels): ${MODE}"
        continue
    fi

    if [ "${DRY_RUN}" != "1" ] && [ ! -f "${DEST}/${OPT}" ]; then
        die "Optimization result not found: ${DEST}/${OPT}"
    fi
    log "---- ${MODE}: placing the optimization result in staging and regenerating Phases 7/8 ----"
    protect_file "${SET}" "${OPT}"   # stash an existing file with the same name (restored at the end)
    run cp -p "${DEST}/${OPT}" "${TD}/${SET}/${OPT}"
    run_main "${DEST}/log/${MODE}${SFX}_phase7.log" - \
        --phase 7 --query-set "${SET}" --optimization-mode "${MODE}" --exp-suffix "${SFX}" --use-docker \
        || die "Phase 7 failed (${MODE})"
    run_main "${DEST}/log/${MODE}${SFX}_phase8.log" - \
        --phase 8 --query-set "${SET}" --optimization-mode "${MODE}" --exp-suffix "${SFX}" --use-docker \
        || die "Phase 8 failed (${MODE})"

    for P in "${TODO[@]}"; do
        RATIO=$(printf "0.%02d" "${P}")
        OUT="benchmark_results_${MODE}${SFX}_noise${P}.json"
        log "RUN phase9: ${MODE} noise=${P}% (recall=$((100 - P))%)"
        protect_file "${SET}" "${OUT}"
        restart_container
        run_main "${DEST}/log/${MODE}${SFX}_noise${P}.log" - \
            --phase 9 --query-set "${SET}" --benchmark-mode "${MODE}" --exp-suffix "${SFX}" \
            --noise-ratio "${RATIO}" --use-docker --ease \
            || die "Phase 9 failed (${MODE}, noise=${P}%)"
        collect "${SET}" "${DEST}" "${OUT}"
        restore_file "${SET}" "${OUT}"
    done

    # Remove the copy placed in staging and restore the stashed original
    # (the master copy is in ${DEST})
    run rm -f "${TD}/${SET}/${OPT}"
    restore_file "${SET}" "${OPT}"
done

log "==== RQ2 done: ${DEST}/ ===="
