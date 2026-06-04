#!/usr/bin/env python3
"""
短期間・高密度のワークロードを探索する
目標: 1日を24分割（1時間）または1週間を12時間区切りで十分な種類のクエリが実行される
"""

import json
import pandas as pd
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pathlib import Path

print("=" * 80)
print("短期間・高密度ワークロードの分析")
print("=" * 80)

# 両方のワークロードを分析
workloads = [
    {
        'name': 'instance=53',
        'path': 'output/generated_workloads/imdb/serverless/cluster_53/database_1/matching_1d251c0ce20b00ace653b4e602d75063/queries.json'
    },
    {
        'name': 'instance=131',
        'path': 'output/generated_workloads/imdb/serverless/cluster_131/database_0/matching_d4a21fd1e4604a8f437fa2a3f0778655/queries.json'
    }
]

for workload_info in workloads:
    print(f"\n{'=' * 80}")
    print(f"{workload_info['name']}の分析")
    print("=" * 80)
    
    with open(workload_info['path']) as f:
        workload = json.load(f)
    
    # データフレーム作成
    data = []
    for query in workload:
        ts = datetime.fromisoformat(query['arrival_timestamp'])
        filepath = query['filepath']
        filename = Path(filepath).name
        data.append({
            'timestamp': ts,
            'query_file': filename,
            'hour': ts.hour,
            'date': ts.date()
        })
    
    df = pd.DataFrame(data)
    
    print(f"\n総クエリ数: {len(df):,}")
    print(f"ユニーククエリ種類: {df['query_file'].nunique()}")
    
    # 1. 最もクエリが集中している1日を探す
    print("\n" + "-" * 80)
    print("【1日単位分析】最もクエリが多い日TOP5")
    print("-" * 80)
    
    daily_stats = df.groupby('date').agg({
        'query_file': ['count', 'nunique']
    }).reset_index()
    daily_stats.columns = ['date', 'total_queries', 'unique_queries']
    daily_stats = daily_stats.sort_values('total_queries', ascending=False)
    
    for idx, row in daily_stats.head(5).iterrows():
        date = row['date']
        total = row['total_queries']
        unique = row['unique_queries']
        
        # その日の1時間ごとの分布
        day_df = df[df['date'] == date]
        hourly_counts = day_df.groupby('hour')['query_file'].count()
        hourly_unique = day_df.groupby('hour')['query_file'].nunique()
        
        avg_per_hour = hourly_counts.mean() if len(hourly_counts) > 0 else 0
        avg_unique_per_hour = hourly_unique.mean() if len(hourly_unique) > 0 else 0
        max_per_hour = hourly_counts.max() if len(hourly_counts) > 0 else 0
        
        print(f"\n  {date}: 総{total}クエリ, ユニーク{unique}種類")
        print(f"    1時間あたり平均: {avg_per_hour:.1f}クエリ, {avg_unique_per_hour:.1f}種類")
        print(f"    1時間あたり最大: {max_per_hour}クエリ")
        print(f"    活動時間帯: {len(hourly_counts)}時間")
    
    # 2. 最もクエリが集中している1週間を探す
    print("\n" + "-" * 80)
    print("【1週間単位分析】最もクエリが多い週TOP3")
    print("-" * 80)
    
    df['week_start'] = df['timestamp'].dt.to_period('W').apply(lambda r: r.start_time)
    weekly_stats = df.groupby('week_start').agg({
        'query_file': ['count', 'nunique']
    }).reset_index()
    weekly_stats.columns = ['week_start', 'total_queries', 'unique_queries']
    weekly_stats = weekly_stats.sort_values('total_queries', ascending=False)
    
    for idx, row in weekly_stats.head(3).iterrows():
        week_start = row['week_start']
        total = row['total_queries']
        unique = row['unique_queries']
        
        # その週の12時間ごとの分布
        week_df = df[df['week_start'] == week_start]
        
        # 12時間区切り（0-11時, 12-23時）
        week_df['half_day'] = week_df['timestamp'].dt.floor('12h')
        half_day_counts = week_df.groupby('half_day')['query_file'].count()
        half_day_unique = week_df.groupby('half_day')['query_file'].nunique()
        
        avg_per_12h = half_day_counts.mean() if len(half_day_counts) > 0 else 0
        avg_unique_per_12h = half_day_unique.mean() if len(half_day_unique) > 0 else 0
        max_per_12h = half_day_counts.max() if len(half_day_counts) > 0 else 0
        
        print(f"\n  {week_start.date()}の週: 総{total}クエリ, ユニーク{unique}種類")
        print(f"    12時間あたり平均: {avg_per_12h:.1f}クエリ, {avg_unique_per_12h:.1f}種類")
        print(f"    12時間あたり最大: {max_per_12h}クエリ")
        print(f"    活動期間: {len(half_day_counts)}×12時間")

    # 3. 最も密度が高い連続24時間
    print("\n" + "-" * 80)
    print("【24時間ウィンドウ分析】最も密度が高い24時間")
    print("-" * 80)
    
    df_sorted = df.sort_values('timestamp')
    best_24h = None
    best_count = 0
    best_unique = 0
    
    for i in range(len(df_sorted)):
        start_time = df_sorted.iloc[i]['timestamp']
        end_time = start_time + timedelta(hours=24)
        
        window_df = df_sorted[(df_sorted['timestamp'] >= start_time) & 
                              (df_sorted['timestamp'] < end_time)]
        
        if len(window_df) > best_count:
            best_count = len(window_df)
            best_unique = window_df['query_file'].nunique()
            best_24h = (start_time, end_time, window_df)
    
    if best_24h:
        start, end, window_df = best_24h
        print(f"\n  期間: {start} - {end}")
        print(f"  総クエリ数: {best_count}")
        print(f"  ユニーククエリ: {best_unique}種類")
        
        # 1時間ごとの分布
        window_df['hour_bin'] = window_df['timestamp'].dt.floor('1h')
        hourly = window_df.groupby('hour_bin').agg({
            'query_file': ['count', 'nunique']
        })
        
        print(f"  1時間あたり平均: {hourly[('query_file', 'count')].mean():.1f}クエリ")
        print(f"  1時間あたり平均ユニーク: {hourly[('query_file', 'nunique')].mean():.1f}種類")
        print(f"  1時間あたり最大: {hourly[('query_file', 'count')].max()}クエリ")

print("\n" + "=" * 80)
print("結論と推奨")
print("=" * 80)

print("""
【要求仕様の確認】
- 1日を24分割（1時間区切り）× 24期間
- 1週間を12時間区切り × 14期間  
- 各期間で多くの種類のクエリが実行される
- JOIN数が多く、JOB/CEBクエリの種類が多い

【現状の課題】
RedSetデータは実際の長期間ワークロードであり、クエリが時間的に分散しています。
そのため、1時間あたりのクエリ数・種類数が少ない傾向があります。

【解決策の提案】
1. より短期間・高密度のRedSetクラスタを探す
2. 最も密度が高い期間だけを抽出する
3. 合成的なワークロードを生成する（既存のJOB/CEBクエリの頻度を人工的に設定）

次のスクリプトで、より高密度のクラスタを探索します。
""")
