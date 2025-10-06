# Materialized View Query Optimization

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](https://github.com/Kaina3/mv-query-optimization)

マテリアライズドビュー選択を用いたクエリ最適化システム

## 📋 概要

このプロジェクトは、ILP（整数線形計画法）を用いてマテリアライズドビューを選択し、クエリ実行時間を最適化するシステムです。

### 主要機能

- **クエリ解析**: PostgreSQL EXPLAIN JSONからクエリプランを解析
- **MV選択最適化**: 5種類のILPアルゴリズムによる最適化
  - Normal ILP
  - BigSubs ILP
  - Utility-based
  - Utility-Capacity
  - Frequency-based
- **クエリ書き換え**: 選択されたMVを使用するようクエリを自動書き換え
- **ベンチマーク**: JOB/CEB/RedBenchでの性能評価

## 🚀 クイックスタート

### 前提条件

- Python 3.10以上
- PostgreSQL 13以上
- Gurobi Optimizer（ライセンス必要）

### インストール

```bash
# リポジトリクローン
git clone https://github.com/Kaina3/mv-query-optimization.git
cd mv-query-optimization

# 依存関係インストール
pip install -r requirements.txt

Then enter the container:

```bash
docker exec -ti mv_exp bash
cd data
# Gurobi設定
gurobi_clp -c "config/gurobi.lic"
```

### データベースセットアップ

```bash
# セットアップスクリプト実行
cd data
bash setup.sh

# PostgreSQLにデータロード
psql -U postgres < setup.sql
```

**ベンチマークデータ**: [JOB (Join Order Benchmark)](https://github.com/viktorleis/job)

### Gurobiライセンス設定

プロジェクトの実行にはGurobiライセンスが必要です。[Gurobi公式サイト](https://www.gurobi.com/)でライセンスを取得してください。

> **Tip**: Docker環境では `WLS Compute Server` ライセンスを使用してください。

## 📚 使用方法

### 基本的な実験フロー

```bash
# 1. クエリファイル準備（初回のみ）
python make_each_sqlfile.py
python sqljson.py

# 2. 実験ディレクトリ作成
chmod +777 make_dirs.sh
./make_dirs.sh

# 3. 実験実行
python experiment.py
```

### CLIスクリプト

#### 実験実行

```bash
# 基本的な実験
python scripts/run_experiment.py --algorithm normal --workload data/workload.json

# 複数アルゴリズム比較
python scripts/run_experiment.py --algorithm all --workload data/workload.json

# 詳細ログ出力
python scripts/run_experiment.py --algorithm normal --workload data/workload.json --verbose
```

#### アルゴリズム比較

```bash
# 結果比較
python scripts/compare_algorithms.py --result-dir Output/experiment_20231201

# CSV出力
python scripts/compare_algorithms.py --result-dir Output/experiment_20231201 --output results.csv
```

#### データベースセットアップ

```bash
# スキーマ作成
python scripts/setup_database.py --schema data/schema.sql

# データロード
python scripts/setup_database.py --data data/insert_queries.sql

# トリガー作成
python scripts/setup_database.py --triggers data/triggers.sql
```

#### クエリ書き換え

```bash
# クエリ書き換え
python scripts/rewrite_queries.py --mv-selections Output/mv_selections.json --queries data/queries/ --output Output/rewritten/
```

### RedBench実験

RedBenchを使用する場合は、`dataset/redbench/run.py`の`DEFAULT_PSQL`定数を変更してください。

## 🧪 テスト

```bash
# 全テスト実行
pytest

# カバレッジレポート
pytest --cov=src --cov-report=html

# 特定のテストのみ
pytest tests/unit/test_query_rewriter.py

# パフォーマンステスト
pytest -m performance
```

## 🏗️ プロジェクト構造

```
mv-query-optimization/
├── src/                    # ソースコード
│   ├── core/              # コアモジュール
│   ├── database/          # データベース操作
│   ├── optimization/      # ILPアルゴリズム
│   ├── rewrite/           # クエリ書き換え
│   └── utils/             # ユーティリティ
├── scripts/               # CLIスクリプト
├── tests/                 # テストコード
├── config/                # 設定ファイル
├── data/                  # データとスキーマ
└── docs/                  # ドキュメント
```

## 📊 対応アルゴリズム

| アルゴリズム | 説明 | 用途 |
|------------|------|------|
| Normal ILP | 基本的なILP定式化 | ベースライン |
| BigSubs ILP | 確率的フリップを使用 | 大規模問題 |
| Utility-based | 効用最大化 | コスト重視 |
| Utility-Capacity | 効用/容量比最大化 | ストレージ制約 |
| Frequency-based | 頻度ベース選択 | 頻出パターン |

## 🐳 Docker環境

### イメージビルド

```bash
# データ準備
cd data
bash setup.sh

# イメージビルド
docker build -t mv_query_opt:1.0 .

# コンテナ起動
docker run -ti -d \
  --shm-size=1g \
  --volume postgres_data:/var/lib/postgresql/data \
  --volume python_data:/home/user/mv-query-optimization \
  --name mv_exp \
  mv_query_opt:1.0
```

### サーバー再起動

```bash
# コンテナ内で実行
kill -SIGINT 1
```

### ファイル転送

```bash
# ホスト→コンテナ
docker cp /path/to/local/files mv_exp:/home/root/

# コンテナ→ホスト
docker cp mv_exp:/home/root/mv-query-optimization/Output/. ./Output/
```

## 🔧 高度な設定

### JOB/CEBクエリ切り替え

`utils.py`の`GET_CEB`値を変更:
- `True`: CEBクエリ使用
- `False`: JOBクエリ使用

### pg_ivm設定（IMMV実験）

```bash
# コンテナ内で実行
wget https://github.com/sraoss/pg_ivm/archive/refs/heads/main.zip
unzip main.zip
apt-get -y install postgresql-server-dev-17
cd pg_ivm-main
make install

# PostgreSQLで有効化
psql -U postgres -c "CREATE EXTENSION pg_ivm;"
echo "shared_preload_libraries = 'pg_ivm'" >> /var/lib/postgresql/data/postgresql.conf

# サーバー再起動
kill -SIGINT 1
```

## 📈 その他の実験

- `compare_insertquery.py`: INSERT クエリ性能比較
- `compare_capacity.py`: ストレージ容量の影響評価
- `compare_topk_beta.py`: Top-K MV選択の評価

## 📝 ライセンス

このプロジェクトは研究目的で開発されています。

## 🤝 貢献

バグ報告や機能提案は Issue でお願いします。

## 📖 参考文献

- [Join Order Benchmark (JOB)](https://github.com/viktorleis/job)
- [pg_ivm - Incremental View Maintenance](https://github.com/sraoss/pg_ivm)

