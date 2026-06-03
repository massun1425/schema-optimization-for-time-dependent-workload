#!/usr/bin/env python3
"""カラムレベルの統計ターゲット設定をリセット"""
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
    'movie_link', 'name', 'person_info', 'role_type', 'title'
]

try:
    conn = psycopg2.connect(
        database=settings.database.database,
        user=settings.database.user,
        password=settings.database.password,
        host='localhost'
    )
    
    reset_count = 0
    with conn.cursor() as cursor:
        print("カラムレベルの統計ターゲット設定をデフォルトにリセット中...\n")
        
        for table in base_tables:
            # このテーブルでデフォルト以外の設定があるカラムを取得
            cursor.execute(f"""
                SELECT attname
                FROM pg_attribute
                WHERE attrelid = '{table}'::regclass
                AND attnum > 0
                AND NOT attisdropped
                AND attstattarget <> -1;
            """)
            
            columns = cursor.fetchall()
            if columns:
                print(f"📊 テーブル: {table}")
                for (col_name,) in columns:
                    try:
                        cursor.execute(f"ALTER TABLE {table} ALTER COLUMN {col_name} SET STATISTICS -1;")
                        print(f"  ✅ {col_name} -> デフォルトにリセット")
                        reset_count += 1
                    except Exception as e:
                        print(f"  ❌ {col_name} リセット失敗: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"\n{'='*80}")
    print(f"✅ 完了: {reset_count}個のカラムをデフォルト設定にリセットしました")
    print(f"次回のANALYZEから、セッションのdefault_statistics_target設定が有効になります")
    
except Exception as e:
    print(f"❌ エラー: {e}")
