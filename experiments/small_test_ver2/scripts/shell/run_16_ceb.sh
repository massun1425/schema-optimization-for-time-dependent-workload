#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job/log"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

# コンテナ再起動関数
restart_container() {
    echo ""
    echo ">>> PostgreSQLコンテナを再起動してキャッシュをクリア..."
    docker restart mv_postgres
    echo ">>> 起動完了を待機中..."
    sleep 15
    # 接続確認
    until docker exec mv_postgres pg_isready -U postgres > /dev/null 2>&1; do
        echo ">>> PostgreSQL起動待ち..."
        sleep 2
    done
    echo ">>> PostgreSQL起動完了"
}


restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_utility_optimization.py \
  --query-set cluster_53 \
  --freq-suffix _instance53 \
  --pruning-method iterative \
  --storage-mb 100 \
  
python ${SCRIPT_DIR}/run_utility_benchmark.py \
  --query-set cluster_53 \
  --freq-suffix _instance53 \
  2>&1 | tee ${OUTPUT_DIR}/log_instance53.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_53 \
  --exp-suffix _instance53 \
  --optimization-mode static \
  --static-timestep average \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_static_average_instance53.txt
echo "完了時刻: $(date)"



restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_53 \
  --optimization-mode dynamic \
  --exp-suffix _instance53 \
  --use-pruning \
  --pruning-parallel \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_instance53.txt
echo "完了時刻: $(date)"

restart_container
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set cluster_53 \
  --exp-suffix _instance53 \
  --optimization-mode adaptive \
  --window-size 2 \
  --use-docker \
  --recalc \
  2>&1 | tee ${OUTPUT_DIR}/log_adaptive_instance53.txt
echo "完了時刻: $(date)"




echo ""
echo "========================================================================"
echo "全実験完了: $(date)"
echo "========================================================================"