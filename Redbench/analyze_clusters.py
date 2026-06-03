#!/usr/bin/env python3
"""
Redbenchデータから最適なクラスタを探す:
- SELECTクエリの割合が高い
- クエリの種類が多様（ユニークなクエリ数が多い）
- 十分なクエリ数がある
"""

import duckdb
import pandas as pd
from pathlib import Path

# データパス
data_path = Path(__file__).parent / "data" / "full_serverless.parquet"

print(f"データファイル: {data_path}")
print(f"存在確認: {data_path.exists()}")
print()

# DuckDB接続
con = duckdb.connect()

# 1. クラスタ/データベースごとのクエリタイプ集計
print("=" * 80)
print("1. クラスタ/データベースごとのクエリタイプ集計")
print("=" * 80)

query1 = f"""
SELECT 
    instance_id,
    database_id,
    query_type,
    COUNT(*) as count
FROM read_parquet('{data_path}')
WHERE query_type IN ('select', 'insert', 'update', 'delete')
GROUP BY instance_id, database_id, query_type
ORDER BY instance_id, database_id, query_type
"""

df_types = con.execute(query1).fetchdf()
print(df_types.head(50))
print(f"\n総行数: {len(df_types)}")

# 2. クラスタ/データベースごとのSELECT割合とクエリ多様性
print("\n" + "=" * 80)
print("2. SELECT割合とクエリ多様性の分析")
print("=" * 80)

query2 = f"""
WITH cluster_stats AS (
    SELECT 
        instance_id,
        database_id,
        COUNT(*) as total_queries,
        COUNT(DISTINCT feature_fingerprint) as unique_queries,
        SUM(CASE WHEN query_type = 'select' THEN 1 ELSE 0 END) as select_count,
        SUM(CASE WHEN query_type = 'insert' THEN 1 ELSE 0 END) as insert_count,
        SUM(CASE WHEN query_type = 'update' THEN 1 ELSE 0 END) as update_count,
        SUM(CASE WHEN query_type = 'delete' THEN 1 ELSE 0 END) as delete_count,
        MIN(arrival_timestamp) as earliest_query,
        MAX(arrival_timestamp) as latest_query
    FROM read_parquet('{data_path}')
    WHERE query_type IN ('select', 'insert', 'update', 'delete')
    GROUP BY instance_id, database_id
)
SELECT 
    instance_id,
    database_id,
    total_queries,
    unique_queries,
    select_count,
    insert_count,
    update_count,
    delete_count,
    ROUND(100.0 * select_count / total_queries, 2) as select_percentage,
    ROUND(100.0 * unique_queries / total_queries, 2) as diversity_score,
    earliest_query,
    latest_query
FROM cluster_stats
WHERE total_queries >= 100  -- 最低100クエリ以上
ORDER BY select_percentage DESC, unique_queries DESC
LIMIT 30
"""

df_clusters = con.execute(query2).fetchdf()
print(df_clusters.to_string())

# 3. 最適なクラスタの推奨
print("\n" + "=" * 80)
print("3. 推奨クラスタ（SELECT割合 >= 80%, ユニーククエリ >= 50）")
print("=" * 80)

recommended = df_clusters[
    (df_clusters['select_percentage'] >= 80.0) &
    (df_clusters['unique_queries'] >= 50)
]

if len(recommended) > 0:
    print("\n推奨クラスタ:")
    print(recommended[['instance_id', 'database_id', 'total_queries', 
                       'unique_queries', 'select_percentage']].to_string())
    
    print("\n\n最も推奨するクラスタ:")
    best = recommended.iloc[0]
    print(f"  instance_id: {best['instance_id']}")
    print(f"  database_id: {best['database_id']}")
    print(f"  総クエリ数: {best['total_queries']}")
    print(f"  ユニーククエリ数: {best['unique_queries']}")
    print(f"  SELECT割合: {best['select_percentage']}%")
    print(f"  多様性スコア: {best['diversity_score']}%")
    print(f"  期間: {best['earliest_query']} ～ {best['latest_query']}")
else:
    print("条件に合うクラスタが見つかりませんでした。")
    print("条件を緩和します（SELECT割合 >= 60%, ユニーククエリ >= 30）...")
    
    recommended = df_clusters[
        (df_clusters['select_percentage'] >= 60.0) &
        (df_clusters['unique_queries'] >= 30)
    ]
    
    if len(recommended) > 0:
        print("\n推奨クラスタ（条件緩和後）:")
        print(recommended[['instance_id', 'database_id', 'total_queries', 
                           'unique_queries', 'select_percentage']].to_string())

# 4. 特定の期間でのクエリ分布（上位3クラスタ）
print("\n" + "=" * 80)
print("4. 上位3クラスタの詳細分析")
print("=" * 80)

for idx in range(min(3, len(df_clusters))):
    cluster = df_clusters.iloc[idx]
    print(f"\n--- クラスタ {idx+1}: instance={cluster['instance_id']}, database={cluster['database_id']} ---")
    
    query3 = f"""
    SELECT 
        DATE_TRUNC('day', arrival_timestamp) as day,
        query_type,
        COUNT(*) as count
    FROM read_parquet('{data_path}')
    WHERE instance_id = {cluster['instance_id']}
      AND database_id = {cluster['database_id']}
      AND query_type IN ('select', 'insert', 'update', 'delete')
    GROUP BY day, query_type
    ORDER BY day, query_type
    LIMIT 20
    """
    
    df_daily = con.execute(query3).fetchdf()
    print(df_daily.to_string())

print("\n" + "=" * 80)
print("分析完了")
print("=" * 80)
