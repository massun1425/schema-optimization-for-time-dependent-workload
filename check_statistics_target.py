#!/usr/bin/env python3
"""テーブルごとの統計ターゲット設定を確認"""
import psycopg2
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config.settings import Settings

settings = Settings()

base_tables = [
    'aka_name', 'aka_title', 'cast_info', 'char_name',
    'comp_cast_type', 'company_name', 'company_type', 'complete_cast',
    'info_type', 'keyword', 'kind_type', 'link_type',
    'movie_companies', 'movie_info', 'movie_info_idx', 'movie_keyword',
    'movie_link', 'name', 'person_info', 'role_type',
    'title', 'comp_cast_type'
]

try:
    conn = psycopg2.connect(
        database=settings.database.database,
        user=settings.database.user,
        password=settings.database.password,
        host='localhost'
    )
    
    with conn.cursor() as cursor:
        # 現在のセッションのdefault_statistics_targetを確認
        cursor.execute("SHOW default_statistics_target;")
        default_target = cursor.fetchone()[0]
        print(f"\nセッションのdefault_statistics_target: {default_target}")
        print("="*80)
        
        # 各テーブルのカラムごとの統計ターゲット設定を確認
        for table in base_tables:
            cursor.execute(f"""
                SELECT 
                    attname as column_name,
                    attstattarget as statistics_target
                FROM pg_attribute
                WHERE attrelid = '{table}'::regclass
                AND attnum > 0
                AND NOT attisdropped
                AND attstattarget <> -1  -- -1はデフォルト設定を使用
                ORDER BY attnum;
            """)
            
            results = cursor.fetchall()
            if results:
                print(f"\n📊 テーブル: {table}")
                print(f"    デフォルト以外の統計ターゲットが設定されているカラム:")
                for col_name, target in results:
                    print(f"      - {col_name}: {target}")
        
        # テーブル全体でデフォルト以外の統計ターゲットが設定されているテーブル数
        cursor.execute("""
            SELECT COUNT(DISTINCT attrelid::regclass::text)
            FROM pg_attribute
            WHERE attnum > 0
            AND NOT attisdropped
            AND attstattarget <> -1
            AND attrelid::regclass::text IN (
                'aka_name', 'aka_title', 'cast_info', 'char_name',
                'comp_cast_type', 'company_name', 'company_type', 'complete_cast',
                'info_type', 'keyword', 'kind_type', 'link_type',
                'movie_companies', 'movie_info', 'movie_info_idx', 'movie_keyword',
                'movie_link', 'name', 'person_info', 'role_type', 'title'
            );
        """)
        count = cursor.fetchone()[0]
        print("\n" + "="*80)
        print(f"✅ デフォルト以外の統計ターゲットが設定されているテーブル数: {count}")
    
    conn.close()
    
except Exception as e:
    print(f"❌ エラー: {e}")
