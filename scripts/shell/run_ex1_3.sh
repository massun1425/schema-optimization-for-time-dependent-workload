#!/bin/bash

# ========================================================================
# フェーズ6（最適化のみ）実験スクリプト: タイムステップ数スケーラビリティ
#
# タイムステップ数 _12_mono 〜 _48_mono を 6 刻み(12,18,24,30,36,42,48)で、
# Dynamic 最適化の「pruning あり」と「pruning なし」の最適化時間を計測する。
#
# 実行順序:
#   1) 先に「pruning あり」を全タイムステップ実行し切る（→ _wp にリネーム）
#   2) その後「pruning なし」に移行。各実行は 24h でタイムアウトさせ、
#      24h を超えたもの(exit 124)が出た時点で以降を打ち切る（break）。
#      （小さい T で解けなければ、より大きい T も自明に解けないため）
#
# ファイル名競合対策:
#   pruning あり/なし は同じ td_mv_optimization_result${SUFFIX}.json に書くため、
#   実行直後に必ずリネームする:
#     pruning あり → ..._wp.json
#     pruning なし → ..._wo.json
#
# 使い方: bash scripts/shell/run_ex1_3.sh
#         nohup bash scripts/shell/run_ex1_3.sh > run_ex1_3.log 2>&1 &
#
# 環境変数:
#   TIMEOUT  pruning なし1実行あたりの打ち切り時間 (default 24h)
#   PY       python 実行体 (default python)
# ========================================================================

set -u

cd "$(dirname "$0")/../.."

SCRIPT_DIR="scripts"
QUERY_SET="job-ceb-2"
OUTPUT_DIR="time_dependent_output/ex1_3/log"
RESULT_DIR="time_dependent_output/ex1_3"
BASE_DIR="time_dependent_output/${QUERY_SET}"   # phase6 の実出力先
PY="${PY:-python}"
TIMEOUT="${TIMEOUT:-24h}"
B_MAX=500
TIMESTEPS=(12 18 24 30 36 42 48)

echo "========================================================================"
echo "実験開始: $(date)"
echo "timesteps=(${TIMESTEPS[*]})  timeout(pruning無)/実行=${TIMEOUT}  B_max=${B_MAX}MB"
echo "========================================================================"

mkdir -p "${OUTPUT_DIR}"
mkdir -p "${RESULT_DIR}"

# 実行直後の結果ファイルを退避リネーム（存在する場合のみ）
rename_result() {
    local suffix=$1
    local tag=$2   # wp | wo
    local src="${BASE_DIR}/td_mv_optimization_result${suffix}.json"
    local dst="${BASE_DIR}/td_mv_optimization_result${suffix}_${tag}.json"
    if [ -f "${src}" ]; then
        mv -f "${src}" "${dst}"
        echo "  → リネーム: ${src} -> ${dst}"
    else
        echo "  ! 警告: 結果ファイルが見つかりません (${src}) — リネームをスキップ"
    fi
}

# ========================================================================
# パス1: pruning あり（全タイムステップ実行し切る）
# ========================================================================
echo ""
echo "########################################################################"
echo "# パス1: Dynamic (pruning あり) — 全タイムステップ"
echo "########################################################################"

for TS in "${TIMESTEPS[@]}"; do
    SUFFIX="_${TS}_mono"

    echo ""
    echo "------------------------------------------------------------------------"
    echo "[${SUFFIX}] Dynamic (pruning あり)  開始: $(date)"
    echo "------------------------------------------------------------------------"

    env PYTHONUNBUFFERED=1 ${PY} ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase 6 \
      --query-set "${QUERY_SET}" \
      --optimization-mode dynamic \
      --exp-suffix "${SUFFIX}" \
      --use-pruning \
      --pruning-parallel \
      --b-max ${B_MAX} \
      --recalc \
      2>&1 | tee "${OUTPUT_DIR}/log_dynamic${SUFFIX}_wp.txt"
    STATUS=${PIPESTATUS[0]}

    if [ ${STATUS} -ne 0 ]; then
        echo "[${SUFFIX}] 警告: pruning あり実行が異常終了 (exit=${STATUS})。次へ継続。"
    else
        rename_result "${SUFFIX}" "wp"
    fi
    echo "[${SUFFIX}] 完了時刻: $(date)"
done

# ========================================================================
# パス2: pruning なし（24h タイムアウト。超過が出た時点で打ち切り）
# ========================================================================
echo ""
echo "########################################################################"
echo "# パス2: Dynamic (pruning なし) — 24h タイムアウト付き"
echo "########################################################################"

for TS in "${TIMESTEPS[@]}"; do
    SUFFIX="_${TS}_mono"

    echo ""
    echo "------------------------------------------------------------------------"
    echo "[${SUFFIX}] Dynamic (pruning なし)  開始: $(date)"
    echo "------------------------------------------------------------------------"

    START=$(date +%s)
    timeout "${TIMEOUT}" env PYTHONUNBUFFERED=1 ${PY} ${SCRIPT_DIR}/run_experiment_normal.py \
      --phase 6 \
      --query-set "${QUERY_SET}" \
      --optimization-mode dynamic \
      --exp-suffix "${SUFFIX}" \
      --b-max ${B_MAX} \
      --recalc \
      2>&1 | tee "${OUTPUT_DIR}/log_dynamic${SUFFIX}_wo.txt"
    STATUS=${PIPESTATUS[0]}
    END=$(date +%s)
    ELAPSED=$((END - START))

    if [ ${STATUS} -eq 124 ]; then
        echo "[${SUFFIX}] RESULT=TIMEOUT (>${TIMEOUT}, 経過 ${ELAPSED}s) — DNF"
        echo "[${SUFFIX}] => この T で解不能。以降(より大きい T)も解不能のため打ち切り。"
        break
    elif [ ${STATUS} -ne 0 ]; then
        echo "[${SUFFIX}] RESULT=ERROR (exit=${STATUS}, 経過 ${ELAPSED}s) — ログ末尾:"
        tail -15 "${OUTPUT_DIR}/log_dynamic${SUFFIX}_wo.txt" | sed "s/^/[${SUFFIX}]   /"
        echo "[${SUFFIX}] => 異常終了のため打ち切り。"
        break
    else
        echo "[${SUFFIX}] RESULT=OK (経過 ${ELAPSED}s)"
        rename_result "${SUFFIX}" "wo"
    fi
    echo "[${SUFFIX}] 完了時刻: $(date)"
done

echo ""
echo "========================================================================"
echo "全実験完了/打ち切り: $(date)"
echo "結果: ${BASE_DIR}  (ログ: ${OUTPUT_DIR})"
echo "========================================================================"
