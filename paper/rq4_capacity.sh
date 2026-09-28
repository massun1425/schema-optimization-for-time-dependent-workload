#!/bin/bash
# ======================================================================
# RQ4 / Experiment 4（Fig.11）: ストレージ制約と総実行時間
#
#   job-ceb-2, Cycles / Evolution and Stagnation / Growth and Spikes
#   B_max = 500, 1000, 1500, 2000 MB, 手法 = Proposed / Static / Adapt
#     b500      : RQ1 Exp1-1 と同一条件 → その結果をコピー（論文でも同一ファイル）
#                 （RQ1 の結果が無い、または REUSE=0 なら実行）
#     b1000以上 : Proposed は並列プルーニング（論文の実行条件どおり）
#   縦軸は summary.total_benchmark_time（Static は初期 MV 構築を含む）。
#
# 出力: time_dependent_output/rq4/{24_2_10,24_mono,24_peak}/b{500,1000,1500,2000}/
# 論文の元データ: time_dependent_output/ex4_ok_{cycle,mono,peak}/b*/
#
# 使い方: bash paper/rq4_capacity.sh
#         SUFFIXES="_24_peak" CAPS="1000 2000" bash paper/rq4_capacity.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a SUFFIXES <<< "${SUFFIXES:-_24_2_10 _24_mono _24_peak}"
read -r -a CAPS <<< "${CAPS:-500 1000 1500 2000}"
SRC_RQ1="${TD}/rq1/exp1_1/job-ceb-2"

log "==== RQ4: 容量 ${CAPS[*]} MB × (${SUFFIXES[*]}) ===="
backup_intermediates job-ceb-2

for SFX in "${SUFFIXES[@]}"; do
    for CAP in "${CAPS[@]}"; do
        DEST="${TD}/rq4/${SFX#_}/b${CAP}"
        log "---- ${SFX} / B_max=${CAP}MB ----"

        if [ "${CAP}" = "${B_MAX}" ]; then
            # RQ1 と同一条件（逐次プルーニング）
            METHODS=(dynamic_seq static adaptive)
        else
            METHODS=(dynamic_par static adaptive)
        fi

        for M in "${METHODS[@]}"; do
            read -r OPT BENCH <<< "$(result_files "${M}" "${SFX}")"
            if is_done "${DEST}/${OPT}" "${DEST}/${BENCH}"; then
                log "SKIP（結果あり）: ${DEST}/${BENCH}"
                continue
            fi
            if [ "${CAP}" = "${B_MAX}" ] && reuse_copy "${SRC_RQ1}" "${DEST}" "${OPT}" "${BENCH}"; then
                continue
            fi
            run_postopt job-ceb-2 "${SFX}" "${M}" "${CAP}" "${DEST}"
        done
    done
done

log "==== RQ4 完了: ${TD}/rq4/ ===="
