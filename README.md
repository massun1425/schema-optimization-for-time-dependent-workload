# 時間依存最適化（マイグレーションコスト考慮）の実行手順

時間依存最適化（time-dependent optimization with migration costs）を実行するための手順を説明します。

## 目次

- [概要](#概要)
- [前提条件・セットアップ](#前提条件セットアップ)
- [実行手順（フェーズ別）](#実行手順フェーズ別)
- [コマンドライン引数リファレンス](#コマンドライン引数リファレンス)
- [実験スクリプト（シェル）](#実験スクリプトシェル)
- [入力・出力ファイル](#入力出力ファイル)
- [ディレクトリ構造](#ディレクトリ構造)
- [トラブルシューティング](#トラブルシューティング)
- [付録: 新規ワークロードの生成（Redbench）](#付録-新規ワークロードの生成redbench)

---

## 概要

時間依存最適化は、複数のタイムステップにわたるワークロード変化とマテリアライズドビュー（MV）のマイグレーションコストを考慮して、最適なMV選択を行います。

### 主要な機能
- 時刻ごとに変化するクエリ頻度に対応
- MVの作成・維持・削除のコストを考慮
- 容量制約（ストレージ予算）を満たしながら最適化
- Gurobi を用いた整数線形計画（ILP）による厳密解の導出

---

## 前提条件・セットアップ

### 1. Python環境

```bash
# 仮想環境を作成・アクティベート
python -m venv .venv
source .venv/bin/activate

# 依存パッケージをインストール
pip install -r requirements.txt
```

### 2. Gurobiライセンス

プロジェクトの実行にはGurobiライセンスが必要です。

1. [Gurobi公式サイト](https://www.gurobi.com/)でライセンスを取得（学術利用は無償）
2. ライセンスファイル（`gurobi.lic`）をプロジェクトルートに配置

### 3. PostgreSQL（Docker）

Dockerfileを使ってIMDBデータ込みのPostgreSQLコンテナをビルド・起動します。

```bash
# コンテナをビルド（初回のみ・数分かかります）
docker build -t imdb-postgres .

# コンテナを起動
docker run -d \
  --name mv_postgres \
  --shm-size=4g \
  --cpuset-cpus="0-7" \
  --memory=16g \
  -p 5432:5432 \
  imdb-postgres

# 起動確認
docker exec mv_postgres pg_isready -U postgres
```

> **注意**: Dockerfileはスキーマ作成・データロード・インデックス作成を自動で行います。
> データを永続化したい場合は `-v <ボリューム名>:/var/lib/postgresql` を `docker run` に追加してください。

---

## 実行手順（フェーズ別）

すべてのコマンドはプロジェクトルートから実行します。

### Phase 1: EXPLAIN JSON生成

```bash
python scripts/run_experiment_normal.py --phase 1 --query-set job --use-docker
```

**出力**: `02_json/{query_set}/*.json`

---

### Phase 2: クエリパース

```bash
python scripts/run_experiment_normal.py --phase 2 --query-set job
```

**出力**: `03_parsed/{query_set}/qp_class.pkl`, `parse_summary.json`

---

### Phase 3: JSONノードID付加

```bash
python scripts/run_experiment_normal.py --phase 3 --query-set job
```

**出力**: `02_json/{query_set}/*.json`（更新）

---

### Phase 4: マイグレーションプラン列挙

```bash
python scripts/run_experiment_normal.py --phase 4 --query-set job
```

**出力**: `04_migration/{query_set}/simple_migration_plans.json`

---

### Phase 5: マイグレーションコスト計算

```bash
python scripts/run_experiment_normal.py --phase 5 --query-set job --use-docker
```

**出力**: `04_migration/{query_set}/simple_migration_costs.json`

---

### Phase 5.5: コスト再計算（Phase 5 直後に必須）

Phase 5 で計算したコストをPickleのノード構造を使って精密に再計算します。

```bash
python scripts/recalculate_costs.py --query-set job --overwrite
```

**出力**: `04_migration/{query_set}/simple_migration_costs.json`（上書き更新）

---

### Phase 6: ILP最適化

Phase 5.5 の再計算済みコストを使用するため、`--recalc` フラグを付けて実行します。

```bash
# 動的モード（デフォルト）
python scripts/run_experiment_normal.py \
  --phase 6 --query-set job \
  --optimization-mode dynamic \
  --recalc --use-docker

# プルーニング使用（大規模データ向け）
python scripts/run_experiment_normal.py \
  --phase 6 --query-set job \
  --optimization-mode dynamic \
  --use-pruning --recalc --use-docker

# ストレージ予算を指定（デフォルト: 100MB）
python scripts/run_experiment_normal.py \
  --phase 6 --query-set job \
  --optimization-mode dynamic \
  --b-max 100 --recalc --use-docker
```

**出力**: `time_dependent_output/{query_set}/td_mv_optimization_result{suffix}.json`

#### 静的モード

```bash
# 静的モード（全タイムステップ平均）
python scripts/run_experiment_normal.py \
  --phase 6 --query-set job \
  --optimization-mode static \
  --static-timestep average \
  --static-algorithm normal \
  --recalc --use-docker
```

**出力**:
- `time_dependent_output/{query_set}/static_mv_optimization_result{suffix}.json`
- `time_dependent_output/{query_set}/static_bigsubs_optimization_result{suffix}.json` （bigsubs の場合）

---

### Phase 7: MV作成SQL生成

```bash
python scripts/run_experiment_normal.py \
  --phase 7 --query-set job \
  --optimization-mode dynamic --use-docker
```

**出力**: `time_dependent_output/{query_set}/timestep_*_*.sql`

---

### Phase 8: クエリ書き換え

```bash
python scripts/run_experiment_normal.py \
  --phase 8 --query-set job \
  --optimization-mode dynamic --use-docker
```

**出力**: `time_dependent_output/{query_set}/jobs/timestep_*_*/`

---

### Phase 9: ベンチマーク実行

```bash
# 動的MV
python scripts/run_experiment_normal.py \
  --phase 9 --query-set job \
  --benchmark-mode dynamic --use-docker

# 静的MV
python scripts/run_experiment_normal.py \
  --phase 9 --query-set job \
  --benchmark-mode static --use-docker

# ベースライン（MVなし）
python scripts/run_experiment_normal.py \
  --phase 9 --query-set job \
  --benchmark-mode baseline --use-docker
```

**出力**: `time_dependent_output/{query_set}/benchmark_results_{mode}{suffix}.json`

---

### まとめ：標準的な実行フロー

```bash
# Phase 1〜5：前処理
python scripts/run_experiment_normal.py --phase 1 --query-set job --use-docker
python scripts/run_experiment_normal.py --phase 2 --query-set job
python scripts/run_experiment_normal.py --phase 3 --query-set job
python scripts/run_experiment_normal.py --phase 4 --query-set job
python scripts/run_experiment_normal.py --phase 5 --query-set job --use-docker

# Phase 5.5：コスト再計算（必須）
python scripts/recalculate_costs.py --query-set job --overwrite

# Phase 6〜9：最適化・ベンチマーク
python scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode dynamic --recalc --use-docker
python scripts/run_experiment_normal.py --phase 7 --query-set job --optimization-mode dynamic --use-docker
python scripts/run_experiment_normal.py --phase 8 --query-set job --optimization-mode dynamic --use-docker
python scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode dynamic --use-docker
```

シェルスクリプト（`scripts/shell/run_16_*.sh`）を使うと上記をまとめて実行できます。

---

## コマンドライン引数リファレンス

### フェーズ一覧

| 値 | 説明 |
|----|------|
| `all` | 全フェーズ（1-9）を順次実行 |
| `post-opt` | Phase 6-9 を実行（最適化以降） |
| `0` | データベースセットアップ |
| `1` | EXPLAIN JSON生成 |
| `2` | クエリパース |
| `3` | JSONノードID付加 |
| `4` | マイグレーションプラン列挙 |
| `5` | マイグレーションコスト計算 |
| `6` | ILP最適化（動的/静的） |
| `6.5` | 静的最適化のみ |
| `7` | MV作成SQL生成 |
| `8` | クエリ書き換え |
| `9` | ベンチマーク実行 |

### 主要引数

| 引数 | 値 | デフォルト | 説明 |
|------|-----|---------|------|
| `--phase` | 上記参照 | 必須 | 実行するフェーズ |
| `--query-set` | 文字列 | `job` | クエリセット名 |
| `--optimization-mode` | `dynamic`, `static`, `adaptive` | `dynamic` | 最適化モード |
| `--benchmark-mode` | `dynamic`, `adaptive`, `static`, `baseline` | `dynamic` | ベンチマークモード |
| `--exp-suffix` | 文字列 | 空 | 実験識別サフィックス（例: `_16_2`） |
| `--b-max` | 数値(MB) | `100.0` | ストレージ予算 |
| `--recalc` | フラグ | - | 再計算済みコストを使用（Phase 6 で推奨） |

### プルーニング引数

| 引数 | 値 | デフォルト | 説明 |
|------|-----|---------|------|
| `--use-pruning` | フラグ | - | CF Pruningを使用（大規模データ向け） |
| `--pruning-parallel` | フラグ | - | プルーニングを並列実行 |
| `--pruning-workers` | 整数 | CPUコア数 | プルーニング並列ワーカー数 |

推奨ワーカー数の目安：
- 小規模（〜100候補）: `16`
- 中規模（〜500候補）: `32`
- 大規模（1000+候補）: `48-64`

### 静的最適化引数

| 引数 | 値 | デフォルト | 説明 |
|------|-----|---------|------|
| `--static-timestep` | `first`, `last`, `average`, `addmv` | `last` | 静的最適化で使用するタイムステップ |
| `--static-algorithm` | `normal`, `bigsubs`, `both`, `utility` | `normal` | 静的最適化アルゴリズム |

### コスト推定引数

| 引数 | 説明 |
|------|------|
| `--use-sampling` | サンプリングを使用してコスト推定（Phase 5） |
| `--sampling-parallel` | サンプリングを並列実行 |
| `--sampling-workers` | サンプリング並列ワーカー数 |

### ベンチマーク引数

| 引数 | 値 | デフォルト | 説明 |
|------|-----|---------|------|
| `--noise-ratio` | 0.0〜1.0 | `0.0` | ノイズ注入率（例: `0.2` = 20%のクエリをノイズに置換） |
| `--noise-query-dir` | パス | `01_queries/job` | ノイズ用クエリのディレクトリ |
| `--ease` | フラグ | - | 簡易ベンチマーク（各クエリ1回 × 頻度） |
| `--window-size` | 整数 | `4` | 適応的最適化の移動平均幅 |

### PostgreSQL接続引数

| 引数 | 説明 |
|------|------|
| `--use-docker` | Docker経由でpsqlを実行（推奨） |
| `--use-local` | ローカルのpsqlを使用 |

---

## 実験スクリプト（シェル）

`scripts/shell/` に実験ごとのシェルスクリプトが用意されています。
すべてプロジェクトルートから実行します。

```bash
# 例：Utility最適化の実験
bash scripts/shell/run_16_utility.sh

# バックグラウンドで実行（推奨）
nohup bash scripts/shell/run_16_cap.sh > run.log 2>&1 &
```

| スクリプト | 説明 |
|-----------|------|
| `run_16_baseline.sh` | ベースライン計測（MVなし） |
| `run_16_cap.sh` | 容量制約付き動的最適化 |
| `run_16_ceb.sh` | CEB クエリセットでの実験 |
| `run_16_ceb_wst.sh` | CEB + WSTありでの実験 |
| `run_16_optime.sh` | 最適化時間計測 |
| `run_16_utility.sh` | Utility最適化 |

---

## 入力・出力ファイル

### 入力ファイル

| ファイル | 説明 |
|---------|------|
| `01_queries/{query_set}/*.sql` | SQLクエリファイル |
| `01_queries/{query_set}/frequency_time_dependent{suffix}.json` | タイムステップごとの頻度設定 |
| `config.yaml` | DB接続・実験環境設定 |

### 出力ファイル

| ファイル | 説明 |
|---------|------|
| `02_json/{query_set}/*.json` | EXPLAIN JSON（ノードID付き） |
| `03_parsed/{query_set}/qp_class.pkl` | パース結果（pickle） |
| `04_migration/{query_set}/simple_migration_plans.json` | マイグレーション計画 |
| `04_migration/{query_set}/simple_migration_costs.json` | マイグレーションコスト |
| `time_dependent_output/{query_set}/td_mv_optimization_result{suffix}.json` | 動的最適化結果 |
| `time_dependent_output/{query_set}/static_mv_optimization_result{suffix}.json` | 静的最適化結果 |
| `time_dependent_output/{query_set}/benchmark_results_{mode}{suffix}.json` | ベンチマーク結果 |

---

## ディレクトリ構造

```
mv-query-optimization/
├── scripts/                        # 実行スクリプト
│   ├── run_experiment_normal.py    # メインスクリプト（Phase 1〜9）
│   ├── recalculate_costs.py        # コスト再計算（Phase 5.5）
│   ├── run_utility_optimization.py # Utility最適化
│   ├── run_utility_benchmark.py    # Utilityベンチマーク
│   └── shell/                      # 実験用シェルスクリプト
│       └── run_16_*.sh
├── core/                           # コア最適化ロジック
│   ├── time_dependent_optimizer.py
│   ├── cf_pruner.py                # CF Pruning
│   └── io_loaders.py
├── migration/                      # マイグレーションコスト計算
│   ├── simple_migration_cost_calculator.py
│   ├── sampling_migration_cost_calculator.py
│   └── enumerate_simple_migration_plan.py
├── mv_generation/                  # MV生成SQL
├── src/                            # クエリパース・書き換え
│   ├── core/query_parser.py
│   ├── optimization/
│   └── rewrite/
├── utils/
│   └── postgres_executor.py        # Docker/ローカル切り替え
├── dashboard/                      # 結果可視化ダッシュボード
│   ├── dashboard_api.py            # FastAPI バックエンド
│   └── dashboard.html              # フロントエンド
├── 01_queries/                     # クエリ定義（git管理）
├── 02_json/                        # EXPLAIN出力（gitignore）
├── 03_parsed/                      # パース結果（gitignore）
├── 04_migration/                   # マイグレーション計画（gitignore）
├── time_dependent_output/          # 実験結果（gitignore）
├── Dockerfile                      # PostgreSQL + IMDBコンテナ定義
├── config.yaml                     # 実験環境設定
└── gurobi.lic                      # Gurobiライセンス（gitignore）
```

---

## トラブルシューティング

### Gurobiライセンスエラー

```
gurobipy.GurobiError: No Gurobi license found
```

- [Gurobi公式サイト](https://www.gurobi.com/)で学術ライセンスを取得
- `gurobi.lic` をプロジェクトルートに配置
- または環境変数 `GRB_LICENSE_FILE` にライセンスファイルのパスを設定

### Dockerコンテナが起動しない

```bash
# コンテナの状態確認
docker ps -a | grep mv_postgres

# ログ確認
docker logs mv_postgres | tail -30

# 再ビルドが必要な場合
docker rm mv_postgres
docker build -t imdb-postgres .
docker run -d \
  --name mv_postgres \
  --shm-size=4g \
  --cpuset-cpus="0-7" \
  --memory=16g \
  -p 5432:5432 \
  imdb-postgres
```

### PostgreSQL接続エラー

```bash
# コンテナが起動しているか確認
docker exec mv_postgres pg_isready -U postgres

# コンテナを再起動（キャッシュクリア）
docker restart mv_postgres
sleep 15
```

### pickleファイルが見つからない

Phase 2（クエリパース）を先に実行してください：

```bash
python scripts/run_experiment_normal.py --phase 2 --query-set job
```

### コスト再計算を忘れた場合

Phase 6 実行前に必ず実行してください：

```bash
python scripts/recalculate_costs.py --query-set job --overwrite
```

---

---

## 付録: 新規ワークロードの生成（Redbench）

既存のクエリセット（`01_queries/`）を使う場合は不要です。新しいワークロードを生成する場合のみ参照してください。

Redbench によるワークロード生成自体の手順は [`Redbench/README.md`](Redbench/README.md) を参照してください。Redbench が `workload.csv` を出力したあと、以下の2ステップで本実験で使用できる形式に変換します。

### ステップ1: クエリセットの生成

`workload.csv` から `01_queries/` 以下のSQLファイルと頻度JSONを生成します。

```bash
WORKLOAD_CSV=<workload.csv のパス>
QUERY_SET=<クエリセット名>        # 例: my_workload
START=<開始時刻>                  # 例: 2024-05-25T00:00:00
END=<終了時刻>                    # 例: 2024-05-26T23:59:59
STEP_HOURS=<タイムステップ時間>   # 例: 4
FREQ_SUFFIX=<頻度サフィックス>    # 例: _16_2_10

python scripts/generate_queryset_from_workload_csv.py \
  --csv-path ${WORKLOAD_CSV} \
  --output-query-dir 01_queries/${QUERY_SET} \
  --start ${START} \
  --end   ${END} \
  --step-hours ${STEP_HOURS} \
  --freq-suffix ${FREQ_SUFFIX} \
  --sanitize-ceb
```

| 引数 | 説明 |
|------|------|
| `--csv-path` | Redbench が生成した workload.csv |
| `--output-query-dir` | 出力先（例: `01_queries/cluster_55_53_combined_ex`） |
| `--start` / `--end` | 対象期間の開始・終了時刻 |
| `--step-hours` | タイムステップの時間幅（デフォルト: 4時間） |
| `--freq-suffix` | 頻度JSONファイルの識別サフィックス |
| `--sanitize-ceb` | CEB系クエリを `SELECT COUNT(*)` 形式に変換 |
| `--clean-output` | 出力先の既存 .sql を削除してから生成 |

**出力**:
- `01_queries/<query_set>/*.sql` — SQLクエリファイル
- `01_queries/<query_set>/frequency_time_dependent<suffix>.json` — タイムステップごとの頻度設定

### ステップ2: テーブル名の正規化

Redbench が生成するSQLには `movie_info_1` のようなバージョンサフィックスが付きます。
実際のIMDBデータベースのテーブル名（`movie_info`）に合わせて正規化します。

```bash
python scripts/normalize_queryset_table_versions.py \
  --input-dir 01_queries/${QUERY_SET} \
  --in-place \
  --copy-frequency-json
```

| 引数 | 説明 |
|------|------|
| `--input-dir` | 正規化対象のクエリセットディレクトリ |
| `--in-place` | 入力ディレクトリを直接上書き |
| `--output-dir` | 別ディレクトリに出力する場合に指定（`--in-place` と排他） |
| `--copy-frequency-json` | 頻度JSONもコピー（`--output-dir` 使用時に有効） |

正規化後、`01_queries/<query_set>/` が本実験のフェーズ1以降で使用できる形式になります。
