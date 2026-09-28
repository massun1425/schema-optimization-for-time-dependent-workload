#!/bin/bash
# ======================================================================
# 論文の図表をすべて生成する（入力: paper/*.sh の出力 time_dependent_output/rq*/）。
# 出力: paper_figures/output/
#
# 使い方: bash paper_figures/make_all.sh
#         bash paper_figures/make_all.sh --td-dir <dir> --out-dir <dir>   # 各スクリプトへそのまま渡す
# 入力が揃っていない図表はスキップせずエラーにする（不足ファイルを一覧表示）。
# ======================================================================
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
cd "${HERE}/.." || exit 1
PY="${PY:-.venv/bin/python}"

SCRIPTS=(
    setup_frequency_patterns.py        # Fig.5
    setup_redbench_total_count.py      # Fig.6
    rq1_exp1_1_timestep_time.py        # Fig.7
    rq1_exp1_2_timestep_scaling.py     # Fig.8
    rq1_exp1_3_query_scaling.py        # Fig.9
    rq2_prediction_recall.py           # Fig.10
    rq3_pruning.py                     # Table 2
    rq4_capacity.py                    # Fig.11
)

FAILED=()
for S in "${SCRIPTS[@]}"; do
    echo "== ${S}"
    PYTHONDONTWRITEBYTECODE=1 "${PY}" "${HERE}/${S}" "$@" || FAILED+=("${S}")
done

if [ ${#FAILED[@]} -gt 0 ]; then
    echo "失敗: ${FAILED[*]}"
    exit 1
fi
echo "完了"
