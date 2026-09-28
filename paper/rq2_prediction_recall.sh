#!/bin/bash
# ======================================================================
# RQ2 / Experiment 2（Fig.10）: ワークロード予測の recall に対する頑健性
#
#   Redbench_synthetic（_2h_x2_50x）, B_max = 500MB
#   recall = 100 - noise(%)。noise = 5, 10, ..., 50%
#   各クエリ実行を確率 noise で「元クエリ（MV 未使用）」に差し替える（--noise-ratio, --ease）。
#   最適化はやり直さず、recall 100% の最適化結果を使って Phase 7〜9 だけを実行する。
#   Adapt は将来予測を使わないため noise の影響を受けず、recall 100% の 1 本のみ。
#
# 手順:
#   1) recall 100%: RQ1 Exp1-1 の Redbench 結果をコピー（論文でも同一ファイル）。
#      RQ1 の結果が無い、または REUSE=0 の場合はここで post-opt を実行する。
#   2) Proposed / Static それぞれについて、最適化結果を staging に置いて
#      Phase 7（MV SQL）と Phase 8（書き換え）を再生成し、noise ごとに Phase 9 を実行する。
#
# 出力: time_dependent_output/rq2/
#   benchmark_results_{dynamic,static}_2h_x2_50x{,_noise5,...,_noise50}.json
#   benchmark_results_adaptive_w4_2h_x2_50x.json, 各最適化結果, log/
# 論文の元データ: time_dependent_output/ex2_500M_ok/
#
# 使い方: bash paper/rq2_prediction_recall.sh
#         NOISE_PCTS="5 10" bash paper/rq2_prediction_recall.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

SET="Redbench_synthetic"
SFX="_2h_x2_50x"
DEST="${TD}/rq2"
SRC_RQ1="${TD}/rq1/exp1_1/${SET}"
read -r -a NOISE_PCTS <<< "${NOISE_PCTS:-5 10 15 20 25 30 35 40 45 50}"

log "==== RQ2: ${SET} (${SFX}), noise = ${NOISE_PCTS[*]} % ===="
backup_intermediates "${SET}"

# 1) recall 100%（noise 0）
for M in dynamic_seq static adaptive; do
    read -r OPT BENCH <<< "$(result_files "${M}" "${SFX}")"
    if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
        log "SKIP（結果あり）: ${DEST}/${BENCH}"
    elif ! reuse_copy "${SRC_RQ1}" "${DEST}" "${OPT}" "${BENCH}"; then
        run_postopt "${SET}" "${SFX}" "${M}" "${B_MAX}" "${DEST}"
    fi
done

# 2) noise > 0: Phase 7/8 を最適化結果から再生成し、Phase 9 を noise ごとに実行
for MODE in dynamic static; do
    if [ "${MODE}" = "dynamic" ]; then
        read -r OPT _ <<< "$(result_files dynamic "${SFX}")"
    else
        read -r OPT _ <<< "$(result_files static "${SFX}")"
    fi

    # 未実行の noise だけを対象にする
    TODO=()
    for P in "${NOISE_PCTS[@]}"; do
        is_done "${DEST}/benchmark_results_${MODE}${SFX}_noise${P}.json" || TODO+=("${P}")
    done
    if [ ${#TODO[@]} -eq 0 ]; then
        log "SKIP（全 noise の結果あり）: ${MODE}"
        continue
    fi

    if [ "${DRY_RUN}" != "1" ] && [ ! -f "${DEST}/${OPT}" ]; then
        die "最適化結果がありません: ${DEST}/${OPT}"
    fi
    log "---- ${MODE}: 最適化結果を staging に配置し Phase 7/8 を再生成 ----"
    protect_file "${SET}" "${OPT}"   # 同名の既存ファイルがあれば一時退避（最後に戻す）
    run cp -p "${DEST}/${OPT}" "${TD}/${SET}/${OPT}"
    run_main "${DEST}/log/${MODE}${SFX}_phase7.log" - \
        --phase 7 --query-set "${SET}" --optimization-mode "${MODE}" --exp-suffix "${SFX}" --use-docker \
        || die "Phase 7 失敗 (${MODE})"
    run_main "${DEST}/log/${MODE}${SFX}_phase8.log" - \
        --phase 8 --query-set "${SET}" --optimization-mode "${MODE}" --exp-suffix "${SFX}" --use-docker \
        || die "Phase 8 失敗 (${MODE})"

    for P in "${TODO[@]}"; do
        RATIO=$(printf "0.%02d" "${P}")
        OUT="benchmark_results_${MODE}${SFX}_noise${P}.json"
        log "RUN phase9: ${MODE} noise=${P}% (recall=$((100 - P))%)"
        protect_file "${SET}" "${OUT}"
        restart_container
        run_main "${DEST}/log/${MODE}${SFX}_noise${P}.log" - \
            --phase 9 --query-set "${SET}" --benchmark-mode "${MODE}" --exp-suffix "${SFX}" \
            --noise-ratio "${RATIO}" --use-docker --ease \
            || die "Phase 9 失敗 (${MODE}, noise=${P}%)"
        collect "${SET}" "${DEST}" "${OUT}"
        restore_file "${SET}" "${OUT}"
    done

    # staging に置いたコピーを片付け、退避していた元ファイルを戻す（原本は ${DEST} にある）
    run rm -f "${TD}/${SET}/${OPT}"
    restore_file "${SET}" "${OPT}"
done

log "==== RQ2 完了: ${DEST}/ ===="
