import os
import psycopg2
import json

# 指定されたディレクトリ
directory = os.path.join(os.path.dirname(__file__), 'imdb', 'benchmarks')
output_directory = os.path.join(os.path.dirname(__file__), 'RED_JSON')

# 出力フォルダを作成
os.makedirs(output_directory, exist_ok=True)

# PostgreSQL 接続情報
db_config = {
	'dbname': 'imdbload',
	'user': 'postgres',
	'password': 'pass',
	'host': 'localhost',
	'port': 5432
}

count_num = 0

# 再帰的に .sql ファイルを取得して処理
if os.path.exists(directory):
	try:
		# PostgreSQL に接続
		conn = psycopg2.connect(**db_config)
		cursor = conn.cursor()

		for root, _, files in os.walk(directory):
			for file in files:
				if file.endswith('.sql'):
					count_num += 1
					sql_file_path = os.path.join(root, file)

					# .sql ファイルの内容を読み込む
					with open(sql_file_path, 'r') as f:
						sql_query = f.read()

					# EXPLAIN (FORMAT JSON) を付けて実行
					explain_query = f"EXPLAIN (FORMAT JSON) {sql_query}"
					cursor.execute(explain_query)
					result = cursor.fetchone()[0]  # 結果を取得

					# 結果を JSON ファイルに保存
					output_file_path = os.path.join(output_directory, f"{os.path.splitext(file)[0]}.json")
					with open(output_file_path, 'w') as json_file:
						json.dump(result, json_file, indent=4)

					# if count_num <= 10:
					# 	print(f"Processed: {sql_file_path}")

		print(f"Number of .sql files processed: {count_num}")

	except Exception as e:
		print(f"Error: {e}")
	finally:
		if 'cursor' in locals():
			cursor.close()
		if 'conn' in locals():
			conn.close()
else:
	print(f"Directory '{directory}' does not exist.")