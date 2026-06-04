#!/usr/bin/env python3
"""生成されたワークロードのクエリ種類を分析"""
import json
from pathlib import Path
from collections import Counter

# ワークロードファイルのパス
workload_path = Path("output/generated_workloads/imdb/serverless/cluster_105/database_0/matching_37155ec746c3b8ce3cf4b0f4820693b6/queries.json")

print(f"ワークロード: {workload_path}")
print()

# JSONファイルを読み込み
with open(workload_path, 'r') as f:
    queries = json.load(f)

print(f"総クエリ数: {len(queries)}")
print()

# filepathからクエリタイプを抽出
query_types = []
job_queries = []
ceb_queries = []

for q in queries:
    filepath = q.get('filepath', '')
    
    if filepath:
        # パスから最後のファイル名部分を取得
        query_file = Path(filepath).name
        query_types.append(query_file)
        
        # JOBかCEBかを判定
        if '/job/' in filepath:
            job_queries.append(query_file)
        elif '/ceb/' in filepath:
            ceb_queries.append(query_file)

# カウント
query_counter = Counter(query_types)
job_counter = Counter(job_queries)
ceb_counter = Counter(ceb_queries)

print("=" * 80)
print("JOBクエリの割り当て")
print("=" * 80)
print(f"JOB クエリ種類数: {len(job_counter)}")
print(f"JOB 総出現回数: {sum(job_counter.values())}")
print()

if job_counter:
    print("上位20種類:")
    for query_file, count in job_counter.most_common(20):
        print(f"  {query_file}: {count}回")

print()
print("=" * 80)
print("CEBクエリの割り当て")
print("=" * 80)
print(f"CEB クエリ種類数: {len(ceb_counter)}")
print(f"CEB 総出現回数: {sum(ceb_counter.values())}")
print()

if ceb_counter:
    print("上位20種類:")
    for query_file, count in ceb_counter.most_common(20):
        print(f"  {query_file}: {count}回")

print()
print("=" * 80)
print("全体サマリ")
print("=" * 80)
print(f"ユニークなクエリファイル数: {len(query_counter)}")
print(f"JOB: {len(job_counter)}種類 ({sum(job_counter.values())}回)")
print(f"CEB: {len(ceb_counter)}種類 ({sum(ceb_counter.values())}回)")
print(f"その他: {len(query_counter) - len(job_counter) - len(ceb_counter)}種類")

# 全クエリファイルのリスト
print()
print("=" * 80)
print("全クエリファイル一覧")
print("=" * 80)
for query_file, count in sorted(query_counter.items()):
    query_type = "JOB" if query_file in job_counter else ("CEB" if query_file in ceb_counter else "他")
    print(f"[{query_type}] {query_file}: {count}回")
