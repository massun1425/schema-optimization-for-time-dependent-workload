#!/bin/bash
# ======================================================================
# スケーラビリティ検証: プルーニング「なし」dynamic 最適化（アブレーション）
#
# 目的: プルーニングの効果の大きさを示すため、提案手法(dynamic)を
#       CF Pruning 無しで実行し、最適化(ILP)時間を計測する。
#       全候補MV(数十万件)をそのまま ILP に投入するため、規模が大きいと
#       24時間以内に解けないことが想定される。その場合は「解不能(DNF)」
#       自体が結果となる。
#
# 動作: 指定した複数規模を小さい順に自動実行し、ある規模が 24h で
#       タイムアウト(またはエラー)した時点で break して以降を打ち切る。
#       （20kで解けなければ、より大規模も自明に解けないため）
#       完了済み(no-pruning結果が既にある)の規模は自動スキップする。
#
# 前提: プルーニング済み結果は td_mv_optimization_result_24_mono_wp.json /
#       _seq.json にリネーム退避済み。本スクリプトの出力は空き枠の
#       td_mv_optimization_result_24_mono.json に書かれる(衝突しない)。
#
# 使い方:
#   bash scripts/shell/run_scaling_nopruning.sh                 # 既定リスト
#   bash scripts/shell/run_scaling_nopruning.sh 20000 40000     # 規模を指定
#   nohup bash scripts/shell/run_scaling_nopruning.sh \
#       > progress/scaling_pruning/nopruning.console.log 2>&1 &
#
# 環境変数:
#   TIMEOUT   1規模あたりの打ち切り時間 (default 24h)
#   PY        python 実行体 (default .venv/bin/python)
#   B_MAX     ストレージ予算MB (default 500)
# ======================================================================
set -u

cd "$(dirname "$0")/../.."

if [ "$#" -gt 0 ]; then
    QUERY_COUNTS=("$@")
else
    QUERY_COUNTS=(20000 40000 60000 80000 100000)
fi

PY="${PY:-.venv/bin/python}"
TIMEOUT="${TIMEOUT:-24h}"
FREQ_SUFFIX="_24_mono"
B_MAX="${B_MAX:-500}"
OUT_DIR="progress/scaling_pruning"
mkdir -p "${OUT_DIR}"

echo "======================================================================"
echo "[no-pruning scaling] sizes=(${QUERY_COUNTS[*]})  timeout/規模=${TIMEOUT}  B_max=${B_MAX}MB"
echo "開始: $(date)"
echo "======================================================================"

for N in "${QUERY_COUNTS[@]}"; do
    SET="job-ceb-2-q${N}"
    LOG="${OUT_DIR}/nopruning_q${N}.log"
    RESULT_JSON="time_dependent_output/${SET}/td_mv_optimization_result${FREQ_SUFFIX}.json"

    echo ""
    echo "----------------------------------------------------------------------"
    echo "[${N}] set=${SET}  開始: $(date)"

    if [ ! -f "03_parsed/${SET}/qp_class.pkl" ]; then
        echo "[${N}] SKIP: 03_parsed/${SET}/qp_class.pkl が見つかりません（先に生成してください）"
        continue
    fi

    # 退避漏れ検出: プルーニング済み(pruning_info入り)を上書きしそうなら中断
    if [ -f "${RESULT_JSON}" ] && grep -q '"pruning_info"' "${RESULT_JSON}" 2>/dev/null; then
        echo "[${N}] ABORT: ${RESULT_JSON} はプルーニング済み結果です。先に退避してください。"
        exit 1
    fi

    # 完了済み(no-pruning結果あり=pruning_info無し & solve_time有り)ならスキップ
    if [ -f "${RESULT_JSON}" ] && grep -q '"solve_time_sec"' "${RESULT_JSON}" 2>/dev/null \
       && ! grep -q '"pruning_info"' "${RESULT_JSON}" 2>/dev/null; then
        echo "[${N}] SKIP: no-pruning結果が既にあります (${RESULT_JSON})"
        continue
    fi

    START=$(date +%s)
    # --use-pruning を付けない = 全候補で ILP を解く
    timeout "${TIMEOUT}" env PYTHONUNBUFFERED=1 ${PY} scripts/run_experiment_normal.py \
        --phase 6 \
        --query-set "${SET}" \
        --optimization-mode dynamic \
        --exp-suffix "${FREQ_SUFFIX}" \
        --b-max "${B_MAX}" \
        --recalc \
        2>&1 | tee "${LOG}"

    STATUS=${PIPESTATUS[0]}
    END=$(date +%s)
    ELAPSED=$((END - START))

    if [ ${STATUS} -eq 124 ]; then
        echo "[${N}] RESULT=TIMEOUT (>${TIMEOUT}, 経過 ${ELAPSED}s) — DNF"
        echo "[${N}] => この規模で解不能。以降(より大規模)も解不能のため打ち切り。"
        break
    elif [ ${STATUS} -ne 0 ]; then
        echo "[${N}] RESULT=ERROR (exit=${STATUS}, 経過 ${ELAPSED}s) — ログ末尾:"
        tail -15 "${LOG}" | sed "s/^/[${N}]   /"
        echo "[${N}] => 異常終了。以降を打ち切り。"
        break
    else
        echo "[${N}] RESULT=OK (経過 ${ELAPSED}s)"
        grep -iE "ILP求解時間|フェーズ総実行時間" "${LOG}" | sed "s/^/[${N}] /"
    fi
done

echo ""
echo "======================================================================"
echo "全実験完了/打ち切り: $(date)"
echo "======================================================================"
