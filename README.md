# Materialized View Query Optimization

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![PostgreSQL 18](https://img.shields.io/badge/postgresql-18-blue.svg)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

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

- **Python 3.11以上** (pyenv推奨)
- **Docker Desktop** (PostgreSQLコンテナ用)
- **Gurobi Optimizer 12.0** (ライセンス必要)

### ステップ1: PostgreSQLデータベースセットアップ

#### 1.1 Dockerイメージのビルド

```bash
# IMDBデータを自動ダウンロード・セットアップ (初回は15-20分程度)
docker build -t mv_postgres:1.0 .
```

#### 1.2 PostgreSQLコンテナの起動

```bash
# コンテナ起動 (初回はデータロードに5-10分程度)
docker run -d \
  --name mv_postgres \
  -p 5432:5432 \
  -v mv_postgres_data:/var/lib/postgresql/data \
  mv_postgres:1.0

# 起動確認
docker ps

# データベース接続テスト
docker exec -it mv_postgres psql -U postgres -d imdbload -c "SELECT count(*) FROM title;"

docker exec -it mv_postgres psql -U postgres -d imdbload
```

**接続情報:**
- ホスト: `localhost`
- ポート: `5432`
- データベース: `imdbload`
- ユーザー: `postgres`
- パスワード: `pass`

### ステップ2: Python環境セットアップ

#### 2.1 仮想環境の作成

```bash
# Python 3.11以上を使用
python --version  # 3.11以上であることを確認

# 仮想環境作成
python -m venv .venv

# 仮想環境をアクティベート
source .venv/bin/activate  # macOS/Linux
# または
.venv\Scripts\activate  # Windows
```

#### 2.2 依存パッケージのインストール

```bash
# pipをアップグレード
pip install --upgrade pip

# 依存パッケージインストール
pip install -r requirements.txt
```

### ステップ3: Gurobiライセンス設定

プロジェクトの実行にはGurobiライセンスが必要です。

1. [Gurobi公式サイト](https://www.gurobi.com/)でライセンスを取得
2. ライセンスファイル(`gurobi.lic`)をプロジェクトルートに配置
3. 環境変数を設定（任意）:

```bash
export GUROBI_HOME=/path/to/gurobi
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

**ベンチマークデータ**: [JOB (Join Order Benchmark)](https://github.com/viktorleis/job)

## 📚 使用方法

### 実験実行

```bash
# 仮想環境をアクティベート（毎回必要）
source .venv/bin/activate

# 単一アルゴリズムで実験
python scripts/run_experiment.py --algorithms normal

# 複数アルゴリズムで実験
python scripts/run_experiment.py --algorithms normal bigsubs utility

# すべてのアルゴリズムで実験
python scripts/run_experiment.py --algorithms none normal bigsubs utility utility_capacity frequency

# 詳細ログ出力
python scripts/run_experiment.py --algorithms normal --verbose

# CSV比較を初期化してから実験
python scripts/run_experiment.py --algorithms normal --initialize
```

### データベース接続確認

```bash
# Python から接続テスト
python -c "import psycopg2; conn = psycopg2.connect(host='localhost', port=5432, database='imdbload', user='postgres', password='pass'); print('✓ データベース接続成功')"

# psqlで直接接続
psql -h localhost -p 5432 -U postgres -d imdbload
# パスワード: pass
```

### 実験結果の確認

```bash
# 実験結果は Output/ ディレクトリに保存される
ls -la Output/

# 各ディレクトリの内容:
# - experiment/run_mv/      : MV実行ログ
# - experiment/mv_create/   : MV作成ログ
# - query_rewrite/          : クエリ書き換え結果
# - redbench/               : RedBenchベンチマーク結果
```

## 🧪 テスト

```bash
# 仮想環境をアクティベート
source .venv/bin/activate

# クエリパースのテスト
python scripts/test_query_parse.py

# ILP最適化のテスト (単一アルゴリズム)
python scripts/test_optimization.py --algorithm bigsubs

# MV作成SQL生成のテスト
python scripts/test_mv_generation.py --algorithm bigsubs --max-mvs 5

# 全アルゴリズムのテスト
python scripts/test_optimization.py --algorithm all

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
├── Dockerfile              # PostgreSQLコンテナ定義
├── requirements.txt        # Python依存パッケージ
├── gurobi.lic             # Gurobiライセンス（要配置）
├── src/                   # ソースコード
│   ├── core/              # コアモジュール
│   ├── database/          # データベース操作
│   ├── optimization/      # ILPアルゴリズム
│   ├── rewrite/           # クエリ書き換え
│   └── utils/             # ユーティリティ
├── scripts/               # CLIスクリプト
│   └── run_experiment.py  # 実験実行スクリプト
├── tests/                 # テストコード
├── config/                # 設定ファイル
├── data/                  # データとスキーマ
│   ├── schema.sql         # データベーススキーマ
│   └── setup.sql          # 初期化スクリプト
├── dataset/               # ベンチマークデータセット
│   └── redbench/          # RedBenchデータ
├── Output/                # 実験結果（自動生成）
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

### アーキテクチャ

このプロジェクトは以下の構成で動作します:

- **Dockerコンテナ**: PostgreSQL 18 + IMDBデータベース
- **ホストマシン**: Python実行環境 + プロジェクトコード

この分離により、開発効率とデバッグ容易性が向上します。

### PostgreSQLコンテナ管理

```bash
# コンテナ起動
docker start mv_postgres

# コンテナ停止
docker stop mv_postgres

# コンテナ再起動
docker restart mv_postgres

# コンテナログ確認
docker logs mv_postgres

# コンテナ内でコマンド実行
docker exec -it mv_postgres psql -U postgres -d imdbload

# コンテナ削除（データは保持）
docker rm mv_postgres

# ボリューム含めて完全削除
docker rm -f mv_postgres
docker volume rm mv_postgres_data
```

### データベースの再構築

```bash
# コンテナとボリュームを削除
docker rm -f mv_postgres
docker volume rm mv_postgres_data

# イメージを再ビルド（IMDBデータを再ダウンロード）
docker build -t mv_postgres:1.0 .

# 新しいコンテナを起動
docker run -d \
  --name mv_postgres \
  -p 5432:5432 \
  -v mv_postgres_data:/var/lib/postgresql/data \
  mv_postgres:1.0
```

### トラブルシューティング

#### データベースに接続できない

```bash
# ポート確認
docker port mv_postgres

# コンテナ状態確認
docker ps -a

# ログでエラー確認
docker logs mv_postgres | tail -50
```

#### データがロードされていない

```bash
# テーブル数確認
docker exec -it mv_postgres psql -U postgres -d imdbload -c "\dt"

# レコード数確認
docker exec -it mv_postgres psql -U postgres -d imdbload -c "SELECT 'title' as table_name, count(*) FROM title;"
```

## 🔧 高度な設定

### 開発環境のセットアップ

```bash
# 開発用パッケージのインストール
pip install -r requirements-dev.txt

# コードフォーマット
black src/ tests/

# リント
flake8 src/ tests/

# 型チェック
mypy src/
```

### データベース接続設定のカスタマイズ

プロジェクト内の接続設定は以下のファイルで管理されています:

```python
# src/database/connection.py
DEFAULT_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'imdbload',
    'user': 'postgres',
    'password': 'pass'
}
```

### JOB/CEBクエリ切り替え

`utils.py`の`GET_CEB`値を変更:
- `True`: CEBクエリ使用
- `False`: JOBクエリ使用

### RedBench設定

RedBenchを使用する場合は、`dataset/redbench/run.py`の`DEFAULT_PSQL`定数を変更してください。

## 💡 Tips

### よく使うコマンド

```bash
# 仮想環境アクティベート（毎回必要）
source .venv/bin/activate

# データベース接続確認
docker exec -it mv_postgres psql -U postgres -d imdbload -c "SELECT version();"

# 実験実行（詳細ログ付き）
python scripts/run_experiment.py --algorithms normal --verbose

# 実験結果の確認
ls -lh Output/query_rewrite/

# コンテナのログをリアルタイム表示
docker logs -f mv_postgres
```

### パフォーマンスチューニング

PostgreSQLのパフォーマンスを向上させるには:

```bash
# コンテナ内で設定変更
docker exec -it mv_postgres bash
echo "shared_buffers = 256MB" >> /var/lib/postgresql/data/postgresql.conf
echo "work_mem = 16MB" >> /var/lib/postgresql/data/postgresql.conf
exit

# コンテナ再起動
docker restart mv_postgres
```

## 📈 その他の実験

プロジェクトには以下の実験スクリプトも含まれています:

- `compare_insertquery.py`: INSERT クエリ性能比較
- `compare_capacity.py`: ストレージ容量の影響評価
- `compare_topk_beta.py`: Top-K MV選択の評価

## ❓ FAQ

### Q: Dockerコンテナが起動しない

**A:** Docker Desktopが起動していることを確認してください。

```bash
open -a Docker  # macOS
docker ps       # 起動確認
```

### Q: Python パッケージのインストールに失敗する

**A:** Python 3.11以上を使用していることを確認してください。

```bash
python --version  # 3.11以上であることを確認
python -m venv .venv  # 仮想環境を再作成
source .venv/bin/activate
pip install -r requirements.txt
```

### Q: データベースに接続できない

**A:** PostgreSQLコンテナが起動していることを確認してください。

```bash
docker ps | grep mv_postgres
docker logs mv_postgres | tail -20
```

### Q: 実験結果が出力されない

**A:** Output/ ディレクトリの権限を確認してください。

```bash
mkdir -p Output/{experiment/{run_mv,mv_create},query_rewrite,redbench}
chmod -R 755 Output/
```

## 📝 ライセンス

このプロジェクトは研究目的で開発されています。

## 🤝 貢献

バグ報告や機能提案は Issue でお願いします。

プルリクエストも歓迎します:
1. フォークする
2. フィーチャーブランチを作成 (`git checkout -b feature/AmazingFeature`)
3. 変更をコミット (`git commit -m 'Add some AmazingFeature'`)
4. ブランチにプッシュ (`git push origin feature/AmazingFeature`)
5. プルリクエストを作成

## 📖 参考文献

- [Join Order Benchmark (JOB)](https://github.com/viktorleis/job)
- [PostgreSQL Documentation](https://www.postgresql.org/docs/)
- [Gurobi Optimizer](https://www.gurobi.com/documentation/)

## 🙏 謝辞

このプロジェクトはJOBベンチマークデータセットを使用しています。

---

**開発者**: [Kaina3](https://github.com/Kaina3)  
**最終更新**: 2025年10月7日

