#!/bin/bash
# ======================================================================
# 論文の全実験を順に実行する。
#   RQ2 / RQ3 / RQ4 は RQ1 Exp1-1 の結果を再利用するため、Exp1-1 を最初に実行する。
#   各スクリプトは結果があればスキップするので、途中で止まっても再実行で再開できる。
#
# 使い方: nohup bash paper/run_all.sh > paper_run_all.log 2>&1 &
#         DRY_RUN=1 bash paper/run_all.sh     # 実行されるコマンドの確認のみ
# ======================================================================
set -u -o pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"

STEPS=(
    00_prepare.sh                    # 前処理（既存の入力があればスキップ）
    rq1_exp1_1_timestep_time.sh      # Fig.7
    rq3_pruning.sh                   # Table 2
    rq4_capacity.sh                  # Fig.11
    rq2_prediction_recall.sh         # Fig.10
    rq1_exp1_2_timestep_scaling.sh   # Fig.8  （Phase 6 のみ）
    rq1_exp1_3_query_scaling.sh      # Fig.9  （Phase 6 のみ・長時間）
)

for S in "${STEPS[@]}"; do
    echo "######## $(date '+%F %T') START ${S}"
    bash "${HERE}/${S}" || { echo "######## FAILED: ${S}"; exit 1; }
    echo "######## $(date '+%F %T') END   ${S}"
done
