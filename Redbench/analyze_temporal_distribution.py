#!/usr/bin/env python3
"""
Redbenchワークロードの時系列分布を分析し、最適な時間幅を提案する
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pathlib import Path

# ワークロードパス
workload_json = 'output/generated_workloads/imdb/serverless/cluster_53/database_1/matching_1d251c0ce20b00ace653b4e602d75063/queries.json'
workload_csv = 'output/generated_workloads/imdb/serverless/cluster_53/database_1/matching_1d251c0ce20b00ace653b4e602d75063/workload.csv'

print("=" * 80)
print("Redbenchワークロードの時系列分析")
print("=" * 80)

# JSONからクエリ情報を読み込み
with open(workload_json) as f:
    workload = json.load(f)

print(f"\n総クエリ数: {len(workload):,}")

# 到着時刻を解析
timestamps = []
query_files = []

for query in workload:
    ts = datetime.fromisoformat(query['arrival_timestamp'])
    timestamps.append(ts)
    filepath = query['filepath']
    filename = Path(filepath).name
    query_files.append(filename)

# 時間範囲
min_time = min(timestamps)
max_time = max(timestamps)
duration = max_time - min_time

print(f"\n時間範囲:")
print(f"  開始: {min_time}")
print(f"  終了: {max_time}")
print(f"  期間: {duration.days}日 {duration.seconds // 3600}時間")
print(f"  期間（時間）: {duration.total_seconds() / 3600:.1f}時間")
print(f"  期間（日）: {duration.days + duration.seconds / 86400:.1f}日")

# DataFrameに変換
df = pd.DataFrame({
    'timestamp': timestamps,
    'query_file': query_files
})

print("\n" + "=" * 80)
print("各時間幅での分割案")
print("=" * 80)

# 様々な時間幅での分割を試す
time_divisions = [
    ('1時間', timedelta(hours=1)),
    ('3時間', timedelta(hours=3)),
    ('6時間', timedelta(hours=6)),
    ('12時間', timedelta(hours=12)),
    ('1日', timedelta(days=1)),
    ('3日', timedelta(days=3)),
    ('1週間', timedelta(days=7)),
    ('2週間', timedelta(days=14)),
    ('1ヶ月', timedelta(days=30))
]

results = []

for name, delta in time_divisions:
    # 時間幅で区切る
    num_periods = int((duration.total_seconds() / delta.total_seconds())) + 1
    
    if num_periods == 0:
        continue
    
    # 各期間のクエリ数をカウント
    period_queries = defaultdict(list)
    
    for idx, row in df.iterrows():
        ts = row['timestamp']
        period_idx = int((ts - min_time).total_seconds() / delta.total_seconds())
        period_queries[period_idx].append(row['query_file'])
    
    # 統計計算
    query_counts = [len(queries) for queries in period_queries.values()]
    
    if not query_counts:
        continue
    
    avg_queries = sum(query_counts) / len(query_counts)
    min_queries = min(query_counts)
    max_queries = max(query_counts)
    
    # ユニークなクエリファイル数の平均
    unique_counts = [len(set(queries)) for queries in period_queries.values()]
    avg_unique = sum(unique_counts) / len(unique_counts)
    
    results.append({
        'name': name,
        'num_periods': num_periods,
        'avg_queries': avg_queries,
        'min_queries': min_queries,
        'max_queries': max_queries,
        'avg_unique': avg_unique,
        'delta': delta
    })
    
    print(f"\n【{name}単位で分割】")
    print(f"  期間数: {num_periods}")
    print(f"  期間あたり平均クエリ数: {avg_queries:.1f}")
    print(f"  期間あたり最小クエリ数: {min_queries}")
    print(f"  期間あたり最大クエリ数: {max_queries}")
    print(f"  期間あたり平均ユニーククエリ数: {avg_unique:.1f}")

print("\n" + "=" * 80)
print("推奨される時間幅")
print("=" * 80)

# 条件: 期間数が6-12、各期間に十分なクエリ（100以上）、ユニーククエリも多い
print("\n【推奨条件】")
print("  - 期間数: 6-12（時間依存の変化を観測するのに適切）")
print("  - 各期間のクエリ数: 100以上（統計的に有意）")
print("  - ユニーククエリ: 10以上（多様性）")

print("\n【候補】")
for r in results:
    if 6 <= r['num_periods'] <= 12 and r['avg_queries'] >= 100:
        score = r['avg_unique'] / r['num_periods'] * r['avg_queries'] / 1000
        print(f"  ✓ {r['name']:10s}: 期間数={r['num_periods']:2d}, "
              f"平均クエリ={r['avg_queries']:6.1f}, "
              f"ユニーク={r['avg_unique']:5.1f}")

# 期間数が8付近の推奨
print("\n【最適な分割（8期間付近）】")
for r in results:
    if 7 <= r['num_periods'] <= 9:
        print(f"  {r['name']:10s}: 期間数={r['num_periods']:2d}, "
              f"平均クエリ={r['avg_queries']:6.1f}, "
              f"ユニーク={r['avg_unique']:5.1f}")

# 時系列でのクエリ分布を可視化（1日単位）
print("\n" + "=" * 80)
print("日別クエリ分布（参考）")
print("=" * 80)

df['date'] = df['timestamp'].dt.date
daily_counts = df.groupby('date').size()

print(f"\n日別クエリ数:")
for date, count in daily_counts.items():
    print(f"  {date}: {count:4d}クエリ")

# 週別クエリ分布
df['week'] = df['timestamp'].dt.isocalendar().week
weekly_counts = df.groupby('week').size()

print(f"\n週別クエリ数:")
for week, count in weekly_counts.items():
    print(f"  第{week}週: {count:4d}クエリ")

print("\n" + "=" * 80)
print("結論")
print("=" * 80)
print("""
既存のfrequency_time_dependent_8_1_5.jsonは8期間に分割されています。
instance=53のワークロードを8期間に分割する場合、上記の候補から選択してください。

- 期間数を8にしたい場合: 適切な時間幅を選択
- 各期間に十分なクエリ数を確保: 平均500-1000クエリ程度が理想
- ユニーククエリの多様性: 各期間で15-20種類以上が理想
""")
