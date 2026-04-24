#!/usr/bin/env python3
"""
RedSetクラスタのscanset複雑度を分析し、JOBベンチマークに適したクラスタを探す。
"""

import duckdb
from collections import defaultdict

# DuckDBでParquetを直接クエリ
con = duckdb.connect(':memory:')

parquet_path = 'data/full_serverless.parquet'

print("RedSetデータを読み込み中...")
print("=" * 80)

# 各クラスタのscanset統計を計算
query = """
WITH filtered_queries AS (
    SELECT 
        instance_id,
        database_id,
        read_table_ids,
        num_joins,
        query_type,
        arrival_timestamp,
        CASE 
            WHEN read_table_ids IS NULL THEN 0
            ELSE (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1)
        END as num_tables_in_scanset
    FROM read_parquet(?)
    WHERE query_type = 'select'
      AND num_external_tables_accessed = 0
      AND num_system_tables_accessed = 0
      AND read_table_ids IS NOT NULL
      AND num_joins > 0
      AND was_cached = 0
),
cluster_stats AS (
    SELECT 
        instance_id,
        database_id,
        COUNT(*) as total_queries,
        COUNT(DISTINCT read_table_ids) as unique_scansets,
        AVG(num_tables_in_scanset) as avg_scanset_size,
        MIN(num_tables_in_scanset) as min_scanset_size,
        MAX(num_tables_in_scanset) as max_scanset_size,
        AVG(num_joins) as avg_num_joins,
        MIN(num_joins) as min_num_joins,
        MAX(num_joins) as max_num_joins,
        -- 4テーブル以上のクエリ数
        SUM(CASE WHEN num_tables_in_scanset >= 4 THEN 1 ELSE 0 END) as queries_4plus_tables,
        -- 6テーブル以上のクエリ数
        SUM(CASE WHEN num_tables_in_scanset >= 6 THEN 1 ELSE 0 END) as queries_6plus_tables,
        -- 8テーブル以上のクエリ数
        SUM(CASE WHEN num_tables_in_scanset >= 8 THEN 1 ELSE 0 END) as queries_8plus_tables,
        MIN(arrival_timestamp) as min_timestamp,
        MAX(arrival_timestamp) as max_timestamp
    FROM filtered_queries
    GROUP BY instance_id, database_id
    HAVING total_queries >= 1000  -- 最低1000クエリ以上
)
SELECT *
FROM cluster_stats
WHERE avg_scanset_size >= 3.0  -- 平均3テーブル以上
  AND queries_4plus_tables >= 100  -- 4テーブル以上が100クエリ以上
ORDER BY 
    -- スコアリング: 平均scansetサイズ + 4テーブル以上の割合
    (avg_scanset_size + (queries_4plus_tables::FLOAT / total_queries) * 10) DESC
LIMIT 30
"""

results = con.execute(query, [parquet_path]).fetchdf()

if len(results) == 0:
    print("条件に合うクラスタが見つかりませんでした。")
else:
    print(f"\n見つかったクラスタ: {len(results)}個\n")
    print("=" * 80)
    print("上位クラスタ（scanset複雑度順）:")
    print("=" * 80)
    
    for idx, row in results.iterrows():
        score = row['avg_scanset_size'] + (row['queries_4plus_tables'] / row['total_queries']) * 10
        
        print(f"\n{idx + 1}. instance={row['instance_id']}, database={row['database_id']}")
        print(f"   複雑度スコア: {score:.2f}")
        print(f"   総クエリ数: {row['total_queries']:,}")
        print(f"   ユニークscanset: {row['unique_scansets']:,}")
        print(f"   平均scansetサイズ: {row['avg_scanset_size']:.2f}テーブル")
        print(f"   scansetサイズ範囲: {row['min_scanset_size']:.0f} - {row['max_scanset_size']:.0f}テーブル")
        print(f"   平均JOIN数: {row['avg_num_joins']:.2f}")
        print(f"   JOIN数範囲: {row['min_num_joins']:.0f} - {row['max_num_joins']:.0f}")
        print(f"   4+テーブル: {row['queries_4plus_tables']:,} ({row['queries_4plus_tables']/row['total_queries']*100:.1f}%)")
        print(f"   6+テーブル: {row['queries_6plus_tables']:,} ({row['queries_6plus_tables']/row['total_queries']*100:.1f}%)")
        print(f"   8+テーブル: {row['queries_8plus_tables']:,} ({row['queries_8plus_tables']/row['total_queries']*100:.1f}%)")
        print(f"   期間: {row['min_timestamp']} - {row['max_timestamp']}")

# トップ3の詳細分析
print("\n" + "=" * 80)
print("トップ3クラスタの詳細分析")
print("=" * 80)

for idx in range(min(3, len(results))):
    row = results.iloc[idx]
    instance_id = int(row['instance_id'])
    database_id = int(row['database_id'])
    
    print(f"\n【instance={instance_id}, database={database_id}】")
    
    # scansetサイズの分布を取得
    dist_query = """
    WITH filtered_queries AS (
        SELECT 
            read_table_ids,
            CASE 
                WHEN read_table_ids IS NULL THEN 0
                ELSE (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1)
            END as num_tables_in_scanset
        FROM read_parquet(?)
        WHERE instance_id = ?
          AND database_id = ?
          AND query_type = 'select'
          AND num_external_tables_accessed = 0
          AND num_system_tables_accessed = 0
          AND read_table_ids IS NOT NULL
          AND num_joins > 0
          AND was_cached = 0
    )
    SELECT 
        num_tables_in_scanset,
        COUNT(*) as count,
        COUNT(DISTINCT read_table_ids) as unique_scansets
    FROM filtered_queries
    GROUP BY num_tables_in_scanset
    ORDER BY num_tables_in_scanset
    """
    
    dist = con.execute(dist_query, [parquet_path, instance_id, database_id]).fetchdf()
    
    print("\nscansetサイズ分布:")
    for _, drow in dist.iterrows():
        size = int(drow['num_tables_in_scanset'])
        count = int(drow['count'])
        unique = int(drow['unique_scansets'])
        pct = count / row['total_queries'] * 100
        print(f"  {size:2d}テーブル: {count:6,}クエリ ({pct:5.1f}%), ユニークscanset: {unique:4,}")

print("\n" + "=" * 80)
print("推奨設定:")
print("=" * 80)

if len(results) > 0:
    best = results.iloc[0]
    print(f"\n最も適したクラスタ:")
    print(f"  instance_id = {best['instance_id']}")
    print(f"  database_id = {best['database_id']}")
    print(f"\nワークロード生成コマンド:")
    print(f"  ../.venv/bin/python src/redbench/run.py \\")
    print(f"    --instance_id {best['instance_id']} \\")
    print(f"    --database_id {best['database_id']} \\")
    print(f"    --generation_strategy matching \\")
    print(f"    --config_path_matching config_select_best.json")
    
    # config作成
    import json
    config = {
        "cluster_id": int(best['instance_id']),
        "database_id": int(best['database_id']),
        "only_select": True,
        "use_table_versioning": False
    }
    
    config_filename = f"config_complex_cluster_{int(best['instance_id'])}_{int(best['database_id'])}.json"
    with open(config_filename, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\n設定ファイルを作成しました: {config_filename}")

con.close()
