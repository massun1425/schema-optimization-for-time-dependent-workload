import os
import psycopg2
import json

# PostgreSQLに接続
conn = psycopg2.connect("dbname=imdbload user=postgres")
cur = conn.cursor()

# SQLファイルが格納されているフォルダのパス
sql_folder_path = 'dataset'

# 出力フォルダのパス
output_folder_path = os.path.join(sql_folder_path, 'output')

# 出力フォルダが存在しない場合は作成
if not os.path.exists(output_folder_path):
    os.makedirs(output_folder_path)

# フォルダ内のすべてのSQLファイルを取得
sql_files = [f for f in os.listdir(sql_folder_path) if f.endswith('.sql')]

for sql_file in sql_files:
    sql_file_path = os.path.join(sql_folder_path, sql_file)
    
    # SQLファイルを読み込む
    with open(sql_file_path, 'r', encoding='utf-8') as file:
        sql_query = file.read()
    
    # EXPLAIN結果を取得
    cur.execute(f"EXPLAIN (FORMAT JSON) {sql_query}")
    explain_result = cur.fetchone()
    
    # 結果をJSON形式でファイルに保存
    output_file_path = os.path.join(output_folder_path, f"{os.path.splitext(sql_file)[0]}_explain.json")
    with open(output_file_path, "w", encoding='utf-8') as f:
        json.dump(explain_result[0], f, indent=4)

cur.close()
conn.close()