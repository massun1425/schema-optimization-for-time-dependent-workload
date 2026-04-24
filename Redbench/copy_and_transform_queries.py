#!/usr/bin/env python3
"""
頻度ファイルに含まれるクエリをexperiments/small_test_ver2/01_queries/cluster_53にコピー
JOBクエリ: そのまま
CEBクエリ: SELECT COUNT(*)に統一、ORDER BY/GROUP BYなどを削除
"""

import json
import os
import re
import shutil
from pathlib import Path

def transform_ceb_query(sql_content):
    """
    CEBクエリをSELECT COUNT(*)に変換
    - SELECT句をCOUNT(*)に置き換え
    - ORDER BY、GROUP BY、HAVING、LIMITを削除
    """
    # 複数行を1行にまとめて処理しやすくする
    sql = ' '.join(sql_content.split())
    
    # SELECT句をCOUNT(*)に置き換え
    # SELECT ... FROM のパターンを見つける
    select_pattern = r'SELECT\s+.*?\s+FROM'
    sql = re.sub(select_pattern, 'SELECT COUNT(*) FROM', sql, flags=re.IGNORECASE)
    
    # ORDER BY句を削除
    sql = re.sub(r'\s+ORDER\s+BY\s+[^;]*', '', sql, flags=re.IGNORECASE)
    
    # GROUP BY句を削除
    sql = re.sub(r'\s+GROUP\s+BY\s+[^;]*', '', sql, flags=re.IGNORECASE)
    
    # HAVING句を削除
    sql = re.sub(r'\s+HAVING\s+[^;]*', '', sql, flags=re.IGNORECASE)
    
    # LIMIT句を削除
    sql = re.sub(r'\s+LIMIT\s+\d+', '', sql, flags=re.IGNORECASE)
    
    # セミコロンで終わっていることを確認
    sql = sql.strip()
    if not sql.endswith(';'):
        sql += ';'
    
    # 整形して返す（適度に改行を入れる）
    sql = sql.replace(' FROM ', '\nFROM ')
    sql = sql.replace(' WHERE ', '\nWHERE ')
    sql = sql.replace(' AND ', '\n  AND ')
    sql = sql.replace(' OR ', '\n  OR ')
    
    return sql

def copy_and_transform_queries(frequency_json_path, queries_json_path, target_dir):
    """
    頻度ファイルに含まれるクエリをコピー・変換
    queries.jsonから実際のファイルパスを取得
    """
    # 頻度ファイルを読み込み
    print(f"頻度ファイルを読み込み: {frequency_json_path}")
    with open(frequency_json_path, 'r') as f:
        freq_data = json.load(f)
    
    query_names = set(freq_data['queries'].keys())
    print(f"  クエリ数: {len(query_names)}")
    
    # queries.jsonを読み込み（実際のファイルパスを取得）
    print(f"\nqueries.jsonを読み込み: {queries_json_path}")
    with open(queries_json_path, 'r') as f:
        queries_data = json.load(f)
    
    # クエリ名 -> ファイルパスのマッピングを作成
    query_path_map = {}
    for query in queries_data:
        filepath = query.get('filepath', '')
        query_name = os.path.basename(filepath)
        if query_name in query_names:
            # 既に存在する場合は上書きしない（最初の出現を使用）
            if query_name not in query_path_map:
                query_path_map[query_name] = filepath
    
    print(f"  マッピング作成: {len(query_path_map)}件")
    
    # ターゲットディレクトリを作成
    target_path = Path(target_dir)
    target_path.mkdir(parents=True, exist_ok=True)
    print(f"\nターゲットディレクトリ: {target_dir}")
    
    # 統計
    stats = {
        'job_copied': 0,
        'ceb_transformed': 0,
        'not_found': 0,
        'errors': []
    }
    
    for query_name in sorted(query_names):
        if query_name not in query_path_map:
            stats['not_found'] += 1
            stats['errors'].append(f"マッピングなし: {query_name}")
            print(f"✗ マッピングなし: {query_name}")
            continue
        
        source_path = Path(query_path_map[query_name])
        target_file = target_path / query_name
        
        try:
            if not source_path.exists():
                stats['not_found'] += 1
                stats['errors'].append(f"ファイルなし: {source_path}")
                print(f"✗ ファイルなし: {query_name}")
                continue
            
            # JOBかCEBかはパスから判定
            is_job = '/job/' in str(source_path)
            is_ceb = '/ceb/' in str(source_path)
            
            if is_job:
                # JOBクエリはそのままコピー
                shutil.copy2(source_path, target_file)
                stats['job_copied'] += 1
                print(f"✓ JOB: {query_name}")
            
            elif is_ceb:
                # CEBクエリは変換してコピー
                with open(source_path, 'r', encoding='utf-8') as f:
                    original_sql = f.read()
                
                transformed_sql = transform_ceb_query(original_sql)
                
                with open(target_file, 'w', encoding='utf-8') as f:
                    f.write(transformed_sql)
                
                stats['ceb_transformed'] += 1
                print(f"✓ CEB: {query_name} (変換)")
            
            else:
                # JOBでもCEBでもない（念のためそのままコピー）
                shutil.copy2(source_path, target_file)
                stats['job_copied'] += 1
                print(f"✓ 不明: {query_name} (そのままコピー)")
        
        except Exception as e:
            stats['errors'].append(f"{query_name}: {str(e)}")
            print(f"✗ エラー: {query_name} - {str(e)}")
    
    # 結果サマリー
    print("\n" + "=" * 80)
    print("処理完了")
    print("=" * 80)
    print(f"JOBクエリ（そのままコピー）: {stats['job_copied']}")
    print(f"CEBクエリ（変換）: {stats['ceb_transformed']}")
    print(f"見つからない: {stats['not_found']}")
    print(f"合計処理: {stats['job_copied'] + stats['ceb_transformed']}")
    
    if stats['errors']:
        print(f"\nエラー/警告: {len(stats['errors'])}件")
        for err in stats['errors'][:10]:  # 最初の10件のみ表示
            print(f"  - {err}")
        if len(stats['errors']) > 10:
            print(f"  ... 他{len(stats['errors']) - 10}件")
    
    return stats

def main():
    # パス設定
    frequency_json = "frequency_redbench_instance53_8weeks.json"
    queries_json = "output/generated_workloads/imdb/serverless/cluster_53/database_1/matching_1d251c0ce20b00ace653b4e602d75063/queries.json"
    target_dir = "../experiments/small_test_ver2/01_queries/cluster_53"
    
    # 実行
    stats = copy_and_transform_queries(frequency_json, queries_json, target_dir)
    
    # サンプルCEBクエリの確認
    print("\n" + "=" * 80)
    print("サンプルクエリ（変換後）")
    print("=" * 80)
    
    target_path = Path(target_dir)
    
    # CEBクエリのサンプルを探す
    sample_files = list(target_path.glob("*.sql"))[:5]
    
    if sample_files:
        for sample_file in sample_files:
            print(f"\nファイル: {sample_file.name}")
            print("-" * 80)
            with open(sample_file, 'r') as f:
                content = f.read()
                # 最初の200文字のみ表示
                if len(content) > 200:
                    print(content[:200] + "...")
                else:
                    print(content)

if __name__ == "__main__":
    main()
