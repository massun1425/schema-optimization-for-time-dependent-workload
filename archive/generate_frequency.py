from pathlib import Path
import json
from collections import defaultdict

# job-ceb フォルダのクエリリスト取得
query_dir = Path("experiments/small_test_ver2/01_queries/job-ceb")
query_files = sorted(query_dir.glob("*.sql"))

# JOBとCEBに分類
job_queries = []
ceb_queries = []

for qf in query_files:
    if qf.name.startswith('ceb_'):
        ceb_queries.append(qf.name)
    else:
        job_queries.append(qf.name)

print(f"JOBクエリ数: {len(job_queries)}")
print(f"CEBクエリ数: {len(ceb_queries)}")
print(f"総クエリ数: {len(query_files)}")

# JOBクエリを奇数・偶数で分類
job_odd = []  # 1a, 1b, 3a, 3b, 5a, ...
job_even = []  # 2a, 2b, 4a, 4b, 6a, ...

for qf in job_queries:
    # クエリ番号を抽出（例: 1a.sql → 1）
    num = int(''.join(c for c in qf.split('.')[0] if c.isdigit()))
    if num % 2 == 1:
        job_odd.append(qf)
    else:
        job_even.append(qf)

print(f"\nJOB奇数番号: {len(job_odd)}個")
print(f"JOB偶数番号: {len(job_even)}個")

# CEBクエリをパターン別に分類
ceb_by_pattern = defaultdict(list)

for qf in ceb_queries:
    # ceb_1a_1.sql → 1a
    parts = qf.replace('ceb_', '').split('_')
    pattern = parts[0]
    ceb_by_pattern[pattern].append(qf)

print(f"\nCEBパターン数: {len(ceb_by_pattern)}")
for pattern in sorted(ceb_by_pattern.keys()):
    print(f"  {pattern}: {len(ceb_by_pattern[pattern])}個")

# CEBパターンを2グループに分ける（均等に）
patterns = sorted(ceb_by_pattern.keys())
half = len(patterns) // 2

ceb_group_a_patterns = patterns[:half]
ceb_group_b_patterns = patterns[half:]

ceb_group_a = []
ceb_group_b = []

for pattern in ceb_group_a_patterns:
    ceb_group_a.extend(ceb_by_pattern[pattern])

for pattern in ceb_group_b_patterns:
    ceb_group_b.extend(ceb_by_pattern[pattern])

print(f"\nCEBグループA（パターン: {', '.join(ceb_group_a_patterns)}）: {len(ceb_group_a)}個")
print(f"CEBグループB（パターン: {', '.join(ceb_group_b_patterns)}）: {len(ceb_group_b)}個")

# 最終的なグループ分け
group_a = job_odd + ceb_group_a  # [0,0,0,0,2,2,2,2]
group_b = job_even + ceb_group_b  # [2,2,2,2,0,0,0,0]

print(f"\n最終グループA（頻度 [0,0,0,0,2,2,2,2]）: {len(group_a)}個")
print(f"  JOB奇数: {len(job_odd)}個")
print(f"  CEB: {len(ceb_group_a)}個")

print(f"\n最終グループB（頻度 [2,2,2,2,0,0,0,0]）: {len(group_b)}個")
print(f"  JOB偶数: {len(job_even)}個")
print(f"  CEB: {len(ceb_group_b)}個")

# 頻度ファイル生成
frequency_data = {
    "description": "JOB-CEB Benchmark Frequency Settings (Time-dependent 8 steps)",
    "note": "JOB odd-numbered and CEB patterns (1a-8a): [0,0,0,0,2,2,2,2]. JOB even-numbered and CEB patterns (9a-11b): [2,2,2,2,0,0,0,0].",
    "queries": {}
}

# グループAのクエリ
for qf in sorted(group_a):
    frequency_data["queries"][qf] = [0, 0, 0, 0, 2, 2, 2, 2]

# グループBのクエリ
for qf in sorted(group_b):
    frequency_data["queries"][qf] = [2, 2, 2, 2, 0, 0, 0, 0]

# ファイルに保存
output_path = "experiments/small_test_ver2/01_queries/job-ceb/frequency_time_dependent_8_1.json"
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(frequency_data, f, indent=2, ensure_ascii=False)

print(f"\n✅ 頻度ファイルを作成しました: {output_path}")
print(f"   総クエリ数: {len(frequency_data['queries'])}")
