#!/usr/bin/env python3
"""データ構造確認"""
import duckdb
from pathlib import Path

data_path = Path(__file__).parent / "data" / "full_serverless.parquet"
con = duckdb.connect()

# カラム一覧
query = f"DESCRIBE SELECT * FROM read_parquet('{data_path}') LIMIT 1"
df = con.execute(query).fetchdf()
print("カラム一覧:")
print(df)
