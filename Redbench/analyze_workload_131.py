import json
from collections import Counter
from pathlib import Path

workload_path = 'output/generated_workloads/imdb/serverless/cluster_131/database_0/matching_d4a21fd1e4604a8f437fa2a3f0778655/queries.json'

with open(workload_path) as f:
    workload = json.load(f)

print(f"ワークロード: {workload_path}\n")
print(f"総クエリ数: {len(workload)}\n")

# filepathを抽出
job_queries = []
ceb_queries = []

for query in workload:
    filepath = query['filepath']
    filename = Path(filepath).name
    
    # JOBまたはCEBを判定
    if '/job/' in filepath:
        job_queries.append(filename)
    elif '/ceb/' in filepath:
        ceb_queries.append(filename)

# カウント
job_counter = Counter(job_queries)
ceb_counter = Counter(ceb_queries)

print("=" * 80)
print("JOBクエリの割り当て")
print("=" * 80)
print(f"JOB クエリ種類数: {len(job_counter)}")
print(f"JOB 総出現回数: {sum(job_counter.values())}")

if job_counter:
    print(f"\n上位20種類:")
    for filename, count in job_counter.most_common(20):
        print(f"  {filename}: {count}回")

print("\n" + "=" * 80)
print("CEBクエリの割り当て")
print("=" * 80)
print(f"CEB クエリ種類数: {len(ceb_counter)}")
print(f"CEB 総出現回数: {sum(ceb_counter.values())}")

if ceb_counter:
    print(f"\n上位20種類:")
    for filename, count in ceb_counter.most_common(20):
        print(f"  {filename}: {count}回")

print("\n" + "=" * 80)
print("全体サマリ")
print("=" * 80)
print(f"ユニークなクエリファイル数: {len(job_counter) + len(ceb_counter)}")
print(f"JOB: {len(job_counter)}種類 ({sum(job_counter.values())}回)")
print(f"CEB: {len(ceb_counter)}種類 ({sum(ceb_counter.values())}回)")

# scanset分布も表示
print("\n" + "=" * 80)
print("ベンチマークscanset分布")
print("=" * 80)
scanset_counter = Counter()
for query in workload:
    scanset = tuple(sorted(query['benchmark_scanset']))
    scanset_counter[scanset] += 1

print(f"ユニークなベンチマークscanset数: {len(scanset_counter)}")
print(f"\n上位10個のscanset:")
for scanset, count in scanset_counter.most_common(10):
    pct = count / len(workload) * 100
    print(f"  {len(scanset)}テーブル {scanset}: {count}回 ({pct:.1f}%)")
