#!/usr/bin/env python3
"""
全RedSetクラスタから最も高密度・高多様性の日または週を探す
目標: 1時間あたり15+種類、または12時間あたり15+種類のクエリが実行される期間
"""

import duckdb
from datetime import datetime, timedelta

con = duckdb.connect(':memory:')
parquet_path = 'data/full_serverless.parquet'

print("=" * 80)
print("全RedSetクラスタから高密度・高多様性期間を検索")
print("=" * 80)
print("\nデータを読み込み中...")

# ステップ1: 候補となる高密度クラスタを探す
query_candidate_clusters = """
WITH filtered_queries AS (
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
        END as num_tables_in_scanset,
        DATE_TRUNC('day', arrival_timestamp) as query_date,
        DATE_TRUNC('hour', arrival_timestamp) as query_hour
    FROM read_parquet(?)
    WHERE query_type = 'select'
      AND num_external_tables_accessed = 0
      AND num_system_tables_accessed = 0
      AND read_table_ids IS NOT NULL
      AND num_joins > 0
      AND was_cached = 0
),
daily_stats AS (
    SELECT 
        instance_id,
        database_id,
        query_date,
        COUNT(*) as total_queries,
        COUNT(DISTINCT read_table_ids) as unique_scansets,
        COUNT(DISTINCT feature_fingerprint) as unique_query_patterns,
        AVG(num_tables_in_scanset) as avg_scanset_size,
        AVG(num_joins) as avg_num_joins
    FROM filtered_queries
    GROUP BY instance_id, database_id, query_date
    HAVING total_queries >= 200  -- 1日あたり最低200クエリ
      AND avg_scanset_size >= 4.0  -- 平均4テーブル以上
),
hourly_stats AS (
    SELECT 
        instance_id,
        database_id,
        query_date,
        COUNT(DISTINCT query_hour) as active_hours,
        AVG(hourly_count) as avg_queries_per_hour,
        AVG(hourly_unique) as avg_unique_per_hour,
        MAX(hourly_unique) as max_unique_per_hour
    FROM (
        SELECT 
            instance_id,
            database_id,
            query_date,
            query_hour,
            COUNT(*) as hourly_count,
            COUNT(DISTINCT read_table_ids) as hourly_unique
        FROM filtered_queries
        GROUP BY instance_id, database_id, query_date, query_hour
    )
    GROUP BY instance_id, database_id, query_date
)
SELECT 
    d.instance_id,
    d.database_id,
    d.query_date,
    d.total_queries,
    d.unique_scansets,
    d.unique_query_patterns,
    d.avg_scanset_size,
    d.avg_num_joins,
    h.active_hours,
    h.avg_queries_per_hour,
    h.avg_unique_per_hour,
    h.max_unique_per_hour
FROM daily_stats d
JOIN hourly_stats h USING (instance_id, database_id, query_date)
WHERE h.avg_unique_per_hour >= 8.0  -- 1時間あたり平均8種類以上
   OR h.max_unique_per_hour >= 15    -- または最大15種類以上
ORDER BY h.avg_unique_per_hour DESC, d.total_queries DESC
LIMIT 50
"""

print("\n高密度な日を検索中...")
top_days = con.execute(query_candidate_clusters, [parquet_path]).fetchdf()

if len(top_days) > 0:
    print(f"\n見つかった候補: {len(top_days)}日")
    print("\n" + "=" * 80)
    print("最も有望な日 TOP 20")
    print("=" * 80)
    
    for idx, row in top_days.head(20).iterrows():
        print(f"\n{idx + 1}. instance={row['instance_id']}, database={row['database_id']}, {row['query_date'].date()}")
        print(f"   総クエリ: {row['total_queries']:,}")
        print(f"   ユニークscanset: {row['unique_scansets']}, パターン: {row['unique_query_patterns']}")
        print(f"   平均scansetサイズ: {row['avg_scanset_size']:.1f}テーブル, 平均JOIN: {row['avg_num_joins']:.1f}")
        print(f"   活動時間: {row['active_hours']}時間")
        print(f"   1時間あたり平均: {row['avg_queries_per_hour']:.1f}クエリ, {row['avg_unique_per_hour']:.1f}種類")
        print(f"   1時間あたり最大: {row['max_unique_per_hour']:.0f}種類")
else:
    print("\n条件に合う日が見つかりませんでした。")

# ステップ2: 週単位での検索
print("\n" + "=" * 80)
print("週単位での高密度期間を検索中...")
print("=" * 80)

query_weekly = """
WITH filtered_queries AS (
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
        END as num_tables_in_scanset,
        DATE_TRUNC('week', arrival_timestamp) as week_start,
        DATE_TRUNC('day', arrival_timestamp) as query_date,
        CASE 
            WHEN EXTRACT(hour FROM arrival_timestamp) < 12 THEN 'AM'
            ELSE 'PM'
        END as half_day
    FROM read_parquet(?)
    WHERE query_type = 'select'
      AND num_external_tables_accessed = 0
      AND num_system_tables_accessed = 0
      AND read_table_ids IS NOT NULL
      AND num_joins > 0
      AND was_cached = 0
),
weekly_stats AS (
    SELECT 
        instance_id,
        database_id,
        week_start,
        COUNT(*) as total_queries,
        COUNT(DISTINCT read_table_ids) as unique_scansets,
        COUNT(DISTINCT feature_fingerprint) as unique_query_patterns,
        AVG(num_tables_in_scanset) as avg_scanset_size,
        AVG(num_joins) as avg_num_joins,
        COUNT(DISTINCT query_date) as active_days
    FROM filtered_queries
    GROUP BY instance_id, database_id, week_start
    HAVING total_queries >= 500  -- 1週間で最低500クエリ
      AND avg_scanset_size >= 4.0
      AND active_days >= 5  -- 最低5日活動
),
half_day_stats AS (
    SELECT 
        instance_id,
        database_id,
        week_start,
        AVG(half_day_count) as avg_queries_per_12h,
        AVG(half_day_unique) as avg_unique_per_12h,
        MAX(half_day_unique) as max_unique_per_12h
    FROM (
        SELECT 
            instance_id,
            database_id,
            week_start,
            query_date,
            half_day,
            COUNT(*) as half_day_count,
            COUNT(DISTINCT read_table_ids) as half_day_unique
        FROM filtered_queries
        GROUP BY instance_id, database_id, week_start, query_date, half_day
    )
    GROUP BY instance_id, database_id, week_start
)
SELECT 
    w.instance_id,
    w.database_id,
    w.week_start,
    w.total_queries,
    w.unique_scansets,
    w.unique_query_patterns,
    w.avg_scanset_size,
    w.avg_num_joins,
    w.active_days,
    h.avg_queries_per_12h,
    h.avg_unique_per_12h,
    h.max_unique_per_12h
FROM weekly_stats w
JOIN half_day_stats h USING (instance_id, database_id, week_start)
WHERE h.avg_unique_per_12h >= 10.0  -- 12時間あたり平均10種類以上
   OR h.max_unique_per_12h >= 20    -- または最大20種類以上
ORDER BY h.avg_unique_per_12h DESC, w.total_queries DESC
LIMIT 30
"""

print("\n高密度な週を検索中...")
top_weeks = con.execute(query_weekly, [parquet_path]).fetchdf()

if len(top_weeks) > 0:
    print(f"\n見つかった候補: {len(top_weeks)}週")
    print("\n" + "=" * 80)
    print("最も有望な週 TOP 15")
    print("=" * 80)
    
    for idx, row in top_weeks.head(15).iterrows():
        print(f"\n{idx + 1}. instance={row['instance_id']}, database={row['database_id']}, {row['week_start'].date()}の週")
        print(f"   総クエリ: {row['total_queries']:,}")
        print(f"   ユニークscanset: {row['unique_scansets']}, パターン: {row['unique_query_patterns']}")
        print(f"   平均scansetサイズ: {row['avg_scanset_size']:.1f}テーブル, 平均JOIN: {row['avg_num_joins']:.1f}")
        print(f"   活動日数: {row['active_days']}日")
        print(f"   12時間あたり平均: {row['avg_queries_per_12h']:.1f}クエリ, {row['avg_unique_per_12h']:.1f}種類")
        print(f"   12時間あたり最大: {row['max_unique_per_12h']:.0f}種類")
else:
    print("\n条件に合う週が見つかりませんでした。")

# 最も有望な候補の詳細分析
print("\n" + "=" * 80)
print("推奨")
print("=" * 80)

best_day = None
best_week = None

if len(top_days) > 0:
    best_day = top_days.iloc[0]
    print(f"\n【最良の1日】")
    print(f"  instance={best_day['instance_id']}, database={best_day['database_id']}")
    print(f"  日付: {best_day['query_date'].date()}")
    print(f"  1時間あたり平均{best_day['avg_unique_per_hour']:.1f}種類のユニークscanset")
    print(f"  → 1日24分割ワークロードに使用可能")

if len(top_weeks) > 0:
    best_week = top_weeks.iloc[0]
    print(f"\n【最良の1週間】")
    print(f"  instance={best_week['instance_id']}, database={best_week['database_id']}")
    print(f"  期間: {best_week['week_start'].date()}の週")
    print(f"  12時間あたり平均{best_week['avg_unique_per_12h']:.1f}種類のユニークscanset")
    print(f"  → 1週間14分割ワークロードに使用可能")

print("\n" + "=" * 80)
print("次のステップ")
print("=" * 80)
print("""
上記の候補から選択し、該当期間のワークロードを生成してください。
生成後、JOB/CEBベンチマークとのマッチング品質を確認します。
""")

con.close()
