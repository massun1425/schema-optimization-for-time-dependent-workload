# SELECT クエリのみのワークロード生成 - 実装ガイド

## 方法1: Redbenchコード修正（推奨）

### ステップ1: load_and_preprocess_redset.py を修正

`src/redbench/utils/load_and_preprocess_redset.py` の75行目付近を修正：

```python
# 修正前
def load_and_preprocess_redset(
    ...
    include_all_qtypes: bool = False,
    exclude_tables_never_read: bool = False,
    ...
):
    ...
    # query types to include in the sampling
    query_types = ["select", "insert", "delete", "update"]

# 修正後
def load_and_preprocess_redset(
    ...
    include_all_qtypes: bool = False,
    exclude_tables_never_read: bool = False,
    only_select: bool = False,  # ← 新しいパラメータ
    ...
):
    ...
    # query types to include in the sampling
    if only_select:
        query_types = ["select"]  # ← SELECTのみ
    else:
        query_types = ["select", "insert", "delete", "update"]
```

### ステップ2: matching/utils.py を修正

`src/redbench/matching/utils.py` の `get_query_timeline` 関数を修正：

```python
# 修正前
def get_query_timeline(
    redset_filepath,
    cluster_id,
    database_id,
    start_date,
    end_date,
    redset_exclude_tables_never_read: bool,
    limit_redset_rows_read: int,
):
    con = load_and_preprocess_redset(
        ...
        include_copy=False,
        include_analyze=False,
        include_ctas=False,
        exclude_tables_never_read=redset_exclude_tables_never_read,
        limit_rows=limit_redset_rows_read,
    )

# 修正後
def get_query_timeline(
    redset_filepath,
    cluster_id,
    database_id,
    start_date,
    end_date,
    redset_exclude_tables_never_read: bool,
    limit_redset_rows_read: int,
    only_select: bool = False,  # ← 新しいパラメータ
):
    con = load_and_preprocess_redset(
        ...
        include_copy=False,
        include_analyze=False,
        include_ctas=False,
        exclude_tables_never_read=redset_exclude_tables_never_read,
        limit_rows=limit_redset_rows_read,
        only_select=only_select,  # ← 追加
    )
```

### ステップ3: query_generator.py を修正

`src/redbench/matching/gen_queries/query_generator.py` の150行目付近を修正：

```python
# 修正前
query_timeline = get_query_timeline(
    self.config.redset_path,
    self.config.cluster_id,
    self.config.database_id,
    self.config.start_date,
    self.config.end_date,
    redset_exclude_tables_never_read=redset_exclude_tables_never_read,
    limit_redset_rows_read=self.config.limit_redset_rows_read,
)

# 修正後
only_select = getattr(self.config, "only_select", False)  # ← 設定から読み込み
query_timeline = get_query_timeline(
    self.config.redset_path,
    self.config.cluster_id,
    self.config.database_id,
    self.config.start_date,
    self.config.end_date,
    redset_exclude_tables_never_read=redset_exclude_tables_never_read,
    limit_redset_rows_read=self.config.limit_redset_rows_read,
    only_select=only_select,  # ← 追加
)
```

### ステップ4: config_test.json に設定を追加

```json
{
    "support_benchmarks": [...],
    "start_date": "2024-03-01 00:00:00",
    "end_date": "2024-06-01 00:00:00",
    "matching_method": "scanset",
    "redset_exclude_tables_never_read": false,
    "use_table_versioning": false,
    "limit_redset_rows_read": null,
    "only_select": true  ← 追加！
}
```

### 実行

```bash
python src/redbench/run.py \
  --redset_path data/full_serverless.parquet \
  --output_dir output \
  --generation_strategy matching \
  --config_path_matching config_select_only.json
```

---

## 方法2: 異なるクラスタ/期間でSELECT が多いデータを探す

Redsetデータから SELECT が多い期間を手動で探索：

```bash
python << EOF
import duckdb
con = duckdb.connect()
df = con.execute("""
    SELECT 
        instance_id,
        database_id,
        query_type,
        COUNT(*) as count
    FROM read_parquet('data/full_serverless.parquet')
    WHERE query_type IN ('select', 'insert', 'update', 'delete')
    GROUP BY instance_id, database_id, query_type
    ORDER BY instance_id, database_id, query_type
""").fetchdf()
print(df)
EOF
```

SELECT比率が高いクラスタ/データベースIDを見つけて設定に使用。

---

## 方法3: 既存のJOB/CEBクエリで独自ワークロード生成

プロジェクト内の既存JOBクエリ + 頻度設定ファイルを使用：

`/home/masuda/projects/mv-query-optimization/experiments/small_test_ver2/01_queries/job/`
- 113個のJOBクエリ
- frequency_*.json で時刻変化を定義

この方法なら、Redbenchを使わずに完全にSELECT のみのワークロード。

---

## 推奨

**研究用途 → 方法1（コード修正）**
- 柔軟性が高い
- 現実的なアクセスパターンを保持
- Redsetの多様性を活用

**すぐに実験開始 → 方法3（既存JOB）**
- 修正不要
- 100% SELECT
- 時刻変化も定義済み
