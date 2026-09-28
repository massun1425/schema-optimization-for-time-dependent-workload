#!/bin/bash
# ======================================================================
# RQ1 / Experiment 1-2（Fig.8）: 最適化時間 vs タイムステップ数
#
#   job-ceb-2（2,515 クエリ, 候補 26,312）, Evolution and Stagnation（_{T}_mono）
#   T = 12, 18, 24, 30, 36, 42, B_max = 500MB
#   Phase 6（最適化）のみ実行する。DB は不要。
#     _wp: Proposed（並列プルーニング）
#     _wo: Proposed（プルーニングなし, 1実行あたり ${TIMEOUT} で打ち切り）
#   縦軸は結果 JSON の phase_time_sec。
#
# プルーニングなしの実行がタイムアウトしたら、それより大きい T は打ち切り
# （DNF_{T}_mono_wo.txt を残す）。
#
# 出力: time_dependent_output/rq1/exp1_2/td_mv_optimization_result_{T}_mono_{wp,wo}.json
# 論文の元データ: time_dependent_output/job-ceb-2/result_scaling_time_ok/
#
# 使い方: bash paper/rq1_exp1_2_timestep_scaling.sh
#         TIMESTEPS="12 18" bash paper/rq1_exp1_2_timestep_scaling.sh
# ======================================================================
source "$(dirname "$0")/common.sh"

read -r -a TIMESTEPS <<< "${TIMESTEPS:-12 18 24 30 36 42}"
DEST="${TD}/rq1/exp1_2"

log "==== RQ1 Exp1-2: タイムステップ数 ${TIMESTEPS[*]} ===="

# パス1: プルーニングあり（全 T を実行）
for T in "${TIMESTEPS[@]}"; do
    run_phase6 job-ceb-2 "_${T}_mono" dynamic_par "${B_MAX}" "${DEST}" _wp \
        || die "プルーニングありの最適化に失敗 (T=${T})"
done

# パス2: プルーニングなし（タイムアウトした時点で打ち切り）
for T in "${TIMESTEPS[@]}"; do
    run_phase6 job-ceb-2 "_${T}_mono" dynamic_nopr "${B_MAX}" "${DEST}" _wo "${TIMEOUT}"
    STATUS=$?
    if [ ${STATUS} -eq 124 ]; then
        log "TIMEOUT (> ${TIMEOUT}): T=${T} → DNF。以降の T は打ち切り"
        write_note "${DEST}/DNF_${T}_mono_wo.txt" "DNF: timeout ${TIMEOUT} ($(date '+%F %T'))"
        break
    elif [ ${STATUS} -ne 0 ]; then
        die "プルーニングなしの最適化に失敗 (T=${T}, exit=${STATUS})"
    fi
done

log "==== RQ1 Exp1-2 完了: ${DEST}/ ===="
