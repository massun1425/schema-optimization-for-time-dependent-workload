#!/bin/bash

# 前処理フェーズ（Phase 1〜5 + コスト再計算）を順次実行するスクリプト
# 使い方: bash scripts/shell/run_pre.sh
#         nohup bash scripts/shell/run_pre.sh > pre.log 2>&1 &
# QUERY_SET=Redbench_syntheticでクエリセットを変更

set -e  # エラーが発生したら停止

SCRIPT_DIR="scripts"
QUERY_SET="job"

echo "========================================================================"
echo "前処理開始: $(date)"
echo "クエリセット: ${QUERY_SET}"
echo "========================================================================"

wait_for_postgres() {
    echo ">>> PostgreSQL起動待ち..."
    until docker exec mv_postgres pg_isready -U postgres > /dev/null 2>&1; do
        sleep 2
    done
    echo ">>> PostgreSQL起動完了"
}

wait_for_postgres

echo ""
echo "------------------------------------------------------------------------"
echo "Phase 1: EXPLAIN JSON生成"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 1 \
  --query-set ${QUERY_SET} \
  --use-docker
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "Phase 2: クエリパース"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 2 \
  --query-set ${QUERY_SET}
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "Phase 3: JSONノードID付加"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 3 \
  --query-set ${QUERY_SET}
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "Phase 4: マイグレーションプラン列挙"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 4 \
  --query-set ${QUERY_SET}
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "Phase 5: マイグレーションコスト計算"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase 5 \
  --query-set ${QUERY_SET} \
  --use-sampling \
  --sampling-rate high \
  --use-docker
echo "完了時刻: $(date)"

echo ""
echo "------------------------------------------------------------------------"
echo "Phase 5.5: コスト再計算 (recalculate_costs)"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/recalculate_costs.py \
  --query-set ${QUERY_SET} \
  --overwrite
echo "完了時刻: $(date)"

echo ""
echo "========================================================================"
echo "前処理完了: $(date)"
echo "========================================================================"
