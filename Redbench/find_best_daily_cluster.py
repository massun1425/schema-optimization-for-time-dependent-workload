#!/usr/bin/env python3
"""
全RedSetクラスタから、1日で最もクエリ種類が多い候補を探す（複雑クエリ版）
要件: SELECTのみ、3テーブル以上のJOIN、1日24時間で多様なクエリ種類
"""
import duckdb

con = duckdb.connect(':memory:')
parquet_path = 'data/full_serverless.parquet'

print("=" * 80)
print("全クラスタから1日で最もクエリ種類が多い候補を検索")
print("  条件: 3テーブル以上, JOIN有り, SELECTのみ")
print("=" * 80)

# Step 1: 3テーブル以上のSELECTクエリに限定して分析
query = """
WITH filtered AS (
    SELECT 
        instance_id,
        database_id,
        arrival_timestamp,
        read_table_ids,
        feature_fingerprint,
        num_joins,
        CASE 
            WHEN read_table_ids IS NULL THEN 0
            ELSE (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1)
        END as num_tables,
        DATE_TRUNC('day', arrival_timestamp) as query_date,
        EXTRACT(hour FROM arrival_timestamp) as query_hour
    FROM read_parquet(?)
    WHERE query_type = 'select'
      AND num_external_tables_accessed = 0
      AND num_system_tables_accessed = 0
      AND read_table_ids IS NOT NULL
      AND num_joins >= 2
      AND was_cached = 0
      AND (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1) >= 3
),
daily_stats AS (
    SELECT 
        instance_id,
        database_id,
        query_date,
        COUNT(*) as total_queries,
        COUNT(DISTINCT read_table_ids) as unique_scansets,
        COUNT(DISTINCT feature_fingerprint) as unique_fingerprints,
        AVG(num_tables) as avg_tables,
        AVG(num_joins) as avg_joins,
        MAX(num_tables) as max_tables,
        MAX(num_joins) as max_joins,
        COUNT(DISTINCT query_hour) as active_hours
    FROM filtered
    GROUP BY instance_id, database_id, query_date
    HAVING total_queries >= 30
      AND unique_scansets >= 5
)
SELECT *
FROM daily_stats
ORDER BY unique_scansets DESC
LIMIT 40
"""

print("\n検索中...")
results = con.execute(query, [parquet_path]).fetchdf()

print(f"\n見つかった候補: {len(results)}件\n")
print("=" * 80)
print("TOP40: 1日あたりユニークscanset数ランキング（3テーブル以上）")
print("=" * 80)

for idx, row in results.iterrows():
    print(f"\n{idx+1:2d}. instance={row['instance_id']}, db={row['database_id']}, {row['query_date'].date()}")
    print(f"    総クエリ: {row['total_queries']:,}, ユニークscanset: {row['unique_scansets']}, "
          f"ユニークfp: {row['unique_fingerprints']}")
    print(f"    平均テーブル: {row['avg_tables']:.1f}, 平均JOIN: {row['avg_joins']:.1f}, "
          f"最大テーブル: {row['max_tables']:.0f}, 最大JOIN: {row['max_joins']:.0f}")
    print(f"    活動時間: {row['active_hours']}時間")

# Step 2: 上位候補の時間帯別分布
print("\n\n" + "=" * 80)
print("上位5候補の時間帯別クエリ種類分布")
print("=" * 80)

for idx in range(min(5, len(results))):
    row = results.iloc[idx]
    inst = int(row['instance_id'])
    db = int(row['database_id'])
    date_str = str(row['query_date'].date())
    
    print(f"\n--- #{idx+1}: instance={inst}, db={db}, {date_str} ---")
    
    hourly_query = """
    WITH filtered AS (
        SELECT 
            EXTRACT(hour FROM arrival_timestamp) as hour,
            read_table_ids,
            feature_fingerprint,
            num_joins,
            CASE 
                WHEN read_table_ids IS NULL THEN 0
                ELSE (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1)
            END as num_tables
        FROM read_parquet(?)
        WHERE instance_id = ?
          AND database_id = ?
          AND DATE_TRUNC('day', arrival_timestamp) = ?::TIMESTAMP
          AND query_type = 'select'
          AND num_external_tables_accessed = 0
          AND num_system_tables_accessed = 0
          AND read_table_ids IS NOT NULL
          AND num_joins >= 2
          AND was_cached = 0
          AND (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1) >= 3
    )
    SELECT 
        hour,
        COUNT(*) as count,
        COUNT(DISTINCT read_table_ids) as unique_scansets,
        COUNT(DISTINCT feature_fingerprint) as unique_fps,
        AVG(num_tables) as avg_tables,
        AVG(num_joins) as avg_joins
    FROM filtered
    GROUP BY hour
    ORDER BY hour
    """
    
    hourly = con.execute(hourly_query, [parquet_path, inst, db, date_str]).fetchdf()
    
    if len(hourly) > 0:
        for _, hr in hourly.iterrows():
            bar = '▓' * min(int(hr['unique_scansets']), 60)
            print(f"  {int(hr['hour']):2d}時: {int(hr['count']):4d}ql, {int(hr['unique_scansets']):3d}種(ss), "
                  f"{int(hr['unique_fps']):3d}種(fp), 平均{hr['avg_tables']:.1f}tbl {bar}")

# Step 3: 上位の各クラスタについて、連続した日の分布を確認
print("\n\n" + "=" * 80)
print("上位クラスタの連続日分布")
print("=" * 80)

seen_clusters = set()
for idx in range(len(results)):
    row = results.iloc[idx]
    key = (int(row['instance_id']), int(row['database_id']))
    if key in seen_clusters:
        continue
    seen_clusters.add(key)
    if len(seen_clusters) > 5:
        break
    
    inst, db = key
    print(f"\n--- instance={inst}, db={db}: 全日分布 ---")
    
    multi_day = """
    WITH filtered AS (
        SELECT 
            DATE_TRUNC('day', arrival_timestamp) as query_date,
            read_table_ids,
            feature_fingerprint,
            num_joins,
            CASE 
                WHEN read_table_ids IS NULL THEN 0
                ELSE (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1)
            END as num_tables,
            EXTRACT(hour FROM arrival_timestamp) as query_hour
        FROM read_parquet(?)
        WHERE instance_id = ?
          AND database_id = ?
          AND query_type = 'select'
          AND num_external_tables_accessed = 0
          AND num_system_tables_accessed = 0
          AND read_table_ids IS NOT NULL
          AND num_joins >= 2
          AND was_cached = 0
          AND (LENGTH(read_table_ids) - LENGTH(REPLACE(read_table_ids, ',', '')) + 1) >= 3
    )
    SELECT 
        query_date,
        COUNT(*) as total,
        COUNT(DISTINCT read_table_ids) as unique_ss,
        COUNT(DISTINCT feature_fingerprint) as unique_fp,
        AVG(num_tables) as avg_tbl,
        COUNT(DISTINCT query_hour) as active_hours
    FROM filtered
    GROUP BY query_date
    HAVING total >= 10
    ORDER BY query_date
    """
    
    days = con.execute(multi_day, [parquet_path, inst, db]).fetchdf()
    for _, d in days.iterrows():
        bar = '█' * min(int(d['unique_ss'] / 2), 40)
        print(f"  {d['query_date'].date()}: {int(d['total']):4d}ql, {int(d['unique_ss']):3d}種(ss), "
              f"{int(d['active_hours']):2d}h活動 {bar}")

con.close()
print("\n完了")
