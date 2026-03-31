import json
from collections import Counter
from pathlib import Path

workload_path = 'output/generated_workloads/imdb/serverless/cluster_53/database_1/matching_1d251c0ce20b00ace653b4e602d75063/queries.json'

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
    print(f"\n全JOBクエリ一覧:")
    for filename, count in sorted(job_counter.items(), key=lambda x: x[0]):
        print(f"  {filename}: {count}回")

print("\n" + "=" * 80)
print("CEBクエリの割り当て")
print("=" * 80)
print(f"CEB クエリ種類数: {len(ceb_counter)}")
print(f"CEB 総出現回数: {sum(ceb_counter.values())}")

if ceb_counter:
    print(f"\n上位30種類:")
    for filename, count in ceb_counter.most_common(30):
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
print(f"\n全scanset:")
for scanset, count in sorted(scanset_counter.items(), key=lambda x: -x[1]):
    pct = count / len(workload) * 100
    print(f"  {len(scanset)}テーブル {scanset}: {count}回 ({pct:.1f}%)")

# instance=131との比較
print("\n" + "=" * 80)
print("instance=131との比較")
print("=" * 80)
print(f"{'指標':<30} {'instance=53':>15} {'instance=131':>15}")
print("-" * 80)
print(f"{'総クエリ数':<30} {len(workload):>15,} {7666:>15,}")
print(f"{'JOBクエリ種類':<30} {len(job_counter):>15} {23:>15}")
print(f"{'CEBクエリ種類':<30} {len(ceb_counter):>15} {454:>15}")
print(f"{'ユニークscanset':<30} {len(scanset_counter):>15} {8:>15}")
