#!/bin/bash

# 実験を順次実行するスクリプト
# 使い方: nohup bash run_experiments.sh > experiments.log 2>&1 &

set -e  # エラーが発生したら停止

SCRIPT_DIR="experiments/small_test_ver2/scripts"
OUTPUT_DIR="experiments/small_test_ver2/time_dependent_output/job/log"

echo "========================================================================"
echo "実験開始: $(date)"
echo "========================================================================"

# 実験1: プルーニングなし（ベースライン）
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_1 \
  --use-pruning \
  --pruning-parallel \
  --static-protection \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_16_1.txt
echo "完了時刻: $(date)"

# 実験2: プルーニングあり（逐次実行）
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_2 \
  --use-pruning \
  --pruning-parallel \
  --static-protection \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_16_2.txt
echo "完了時刻: $(date)"

# 実験3: プルーニングあり（並列実行・16ワーカー）
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_3 \
  --use-pruning \
  --pruning-parallel \
  --static-protection \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_16_3.txt
echo "完了時刻: $(date)"

# 実験4: プルーニングあり（並列実行・32ワーカー）
echo ""
echo "------------------------------------------------------------------------"
echo "開始時刻: $(date)"
echo "------------------------------------------------------------------------"
python ${SCRIPT_DIR}/run_experiment_normal.py \
  --phase post-opt \
  --query-set job \
  --optimization-mode dynamic \
  --exp-suffix _16_4 \
  --use-pruning \
  --pruning-parallel \
  --static-protection \
  --use-docker \
  2>&1 | tee ${OUTPUT_DIR}/log_with_pruning_16_4.txt
echo "完了時刻: $(date)"


echo "実験終了: $(date)"