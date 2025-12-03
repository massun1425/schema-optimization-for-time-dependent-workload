# 時間依存最適化（マイグレーションコスト考慮）の実行手順

このREADMEは、`small_test_ver2` 環境で時間依存最適化（time-dependent optimization with migration costs）を実行するための完全な手順を説明します。

## 概要

時間依存最適化は、複数のタイムステップにわたるワークロード変化とマテリアライズドビュー（MV）のマイグレーションコストを考慮して、最適なMV選択を行います。

### 主要な機能
- 時刻ごとに変化するクエリ頻度に対応
- MVの作成・維持・削除のコストを考慮
- 容量制約（ストレージ予算）を満たしながら最適化
- Gurobi を用いた整数線形計画（ILP）による厳密解の導出

---

## データベースの切り替え（小規模実験 vs JOBベンチマーク）

### 1. 小規模実験用データベース（デフォルト）

`mv_small_test` データベースを使用した小規模実験（3クエリ）の場合は、`config.yaml` をそのまま使用できます。

### 2. JOBベンチマーク用IMDBデータベース

113クエリのJOBベンチマークを実行する場合は、以下の手順でIMDBデータベースをセットアップし、設定を切り替えます。

#### ステップ1: IMDBデータベースのセットアップ

```bash
# IMDBデータのダウンロード、データベース作成、データインポート、インデックス作成を一括実行
python experiments/small_test_ver2/scripts/setup_imdb.py --all

# または段階的に実行
python experiments/small_test_ver2/scripts/setup_imdb.py --download      # ダウンロードのみ
python experiments/small_test_ver2/scripts/setup_imdb.py --create-db     # DB作成
python experiments/small_test_ver2/scripts/setup_imdb.py --import-data   # データインポート
python experiments/small_test_ver2/scripts/setup_imdb.py --create-indexes # インデックス作成

# セットアップの検証
python experiments/small_test_ver2/scripts/setup_imdb.py --verify
```

#### ステップ2: config.yaml の設定変更

`experiments/small_test_ver2/config.yaml` を編集し、以下の設定をコメント切り替えします：

```yaml
# データベース接続設定
database:
  # database: mv_small_test  # 小規模実験用（コメントアウト）
  database: imdbload         # JOBベンチマーク用（コメント解除）

# 最適化パラメータ
optimization:
  # storage_limit_mb: 0.01              # 小規模実験用（コメントアウト）
  # storage_limit_bytes: 10240
  storage_limit_mb: 100                 # JOBベンチマーク用（コメント解除）
  storage_limit_bytes: 104857600        # 100MB

# ベンチマーク設定
benchmark:
  # queries_dir: experiments/small_test_ver2/02_json        # 小規模実験用（コメントアウト）
  # sql_dir: experiments/small_test_ver2/01_queries
  queries_dir: dataset/redbench/imdb/benchmarks/job/json   # JOBベンチマーク用（コメント解除）
  sql_dir: dataset/redbench/imdb/benchmarks/job/sql

# クエリ設定
query:
  # num_queries: 3    # 小規模実験用（コメントアウト）
  num_queries: 113    # JOBベンチマーク用（コメント解除）
```

#### ステップ3: JOBベンチマークの実行

設定変更後、通常通り実験スクリプトを実行します：

```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all
```

**注意**: JOBベンチマークは113クエリあるため、小規模実験よりも処理時間が長くなります。

---

## 実行手順

### 前提条件
- Python 3.x がインストールされていること
- Gurobi がインストールされており、ライセンスが有効であること
- 必要なPythonパッケージがインストールされていること（`requirements.txt` を参照）

### クエリセットの選択

`01_queries/` フォルダには複数のクエリセットが用意されています：
- `job_like/`: デフォルトのクエリセット
- `explicit_join/`: 明示的なJOINを使用したクエリセット

`--query-set` オプションでクエリセットを選択できます：

```bash
# job_likeクエリセットを使用（デフォルト）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1 --query-set job_like

# explicit_joinクエリセットを使用
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1 --query-set explicit_join
```

各クエリセットの出力は、対応するサブディレクトリに保存されます：
- `02_json/{query_set}/`: EXPLAIN JSON出力
- `03_parsed/{query_set}/`: パース結果
- `04_optimized/{query_set}/`: 最適化結果
- `05_mv_sql/{query_set}/`: MV生成SQL
- `06_rewritten/{query_set}/`: 書き換えクエリ

### 実験サフィックス（異なる頻度設定の区別）

複数の頻度パターンや周期で実験を行う場合、`--exp-suffix` オプションを使用して実験結果を区別できます：

```bash
# 周期8の実験（frequency_time_dependent_16_2.jsonを使用）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --exp-suffix _16_2

# 周期4の実験（frequency_time_dependent_16_4.jsonを使用）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --exp-suffix _16_4

# サフィックスなし（デフォルト: frequency_time_dependent.jsonを使用）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all
```

**ファイル命名規則**：
- **入力**: `01_queries/{query_set}/frequency_time_dependent{suffix}.json`
- **Phase 6出力**: `time_dependent_output/{query_set}/td_mv_optimization_result{suffix}.json`
- **Phase 9出力**: `time_dependent_output/{query_set}/benchmark_results_{mode}{suffix}.json`
- **Phase 7/8出力**: サフィックスなし（最新の最適化結果に基づく）

詳細は「実験サフィックスの使い方」セクションを参照してください。

### ステップ1: データベースのセットアップとクエリ実行計画の取得

**前提条件**: 実験を開始する前に、データベースのセットアップを完了させてください。

#### データベースセットアップ（実験開始前に1回のみ実行）

```bash
# IMDBデータのダウンロード、データベース作成、データインポート、インデックス作成を一括実行
python experiments/small_test_ver2/scripts/setup_imdb.py --all

# または段階的に実行
python experiments/small_test_ver2/scripts/setup_imdb.py --download      # ダウンロードのみ
python experiments/small_test_ver2/scripts/setup_imdb.py --create-db     # DB作成
python experiments/small_test_ver2/scripts/setup_imdb.py --import-data   # データインポート
python experiments/small_test_ver2/scripts/setup_imdb.py --create-indexes # インデックス作成

# セットアップの検証
python experiments/small_test_ver2/scripts/setup_imdb.py --verify
```

#### フェーズ1: クエリのEXPLAIN JSON生成

データベースセットアップ完了後、各クエリの実行計画（EXPLAIN JSON）を取得します。

```bash
# フェーズ1: クエリのEXPLAIN JSON生成（デフォルトのjob_likeクエリセット）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1

# または特定のクエリセットを指定
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 1 --query-set explicit_join
```

**生成されるファイル**:
- `02_json/{query_set}/query1.json` 〜 `query9.json`: 各クエリのEXPLAIN結果

---

### ステップ2: クエリパース（MV候補の抽出と効用計算）

EXPLAIN結果を解析し、MV候補とその効用を計算します。

```bash
# フェーズ2: クエリパース（デフォルトのjob_likeクエリセット）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 2

# または特定のクエリセットを指定
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 2 --query-set explicit_join
```

**生成されるファイル**:
- `03_parsed/{query_set}/qp_class.pkl`: クエリパーサの出力（u_ij, X, b_j, node_list などを含む）
- `03_parsed/{query_set}/parse_summary.json`: パース結果のサマリー

---

### ステップ3: JSONファイルへのノードID付加

EXPLAIN JSONファイルに各ノードのIDを付加します。

```bash
# フェーズ3: JSONファイルへのノードID付加
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 3 --query-set job
```

**生成されるファイル**:
- `02_json/{query_set}/*.json`: ノードID付きEXPLAIN JSON（上書き更新）

---

### ステップ4: マイグレーションプランの列挙

各MV候補について、作成に必要な依存関係とマイグレーションプラン（SQLレシピ）を列挙します。

```bash
# フェーズ4: マイグレーションプラン列挙
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 4 --query-set job
```

**生成されるファイル**:
- `04_migration/{query_set}/simple_migration_plans.json`: 全MV候補のマイグレーションプラン（SQL）

---

### ステップ5: マイグレーションコストの計算

各マイグレーションプランのコストを計算します。

```bash
# フェーズ5: マイグレーションコスト計算
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 5 --query-set job
```

**生成されるファイル**:
- `04_migration/{query_set}/simple_migration_costs.json`: 各MV候補のレシピとコスト

---

### ステップ6: MV最適化の実行

**最適化モード**を選択してILP最適化を実行します：
- `dynamic` (デフォルト): 時間依存型最適化（マイグレーションコスト考慮）
- `static`: 静的最適化（初期タイムステップのワークロードのみ）

```bash
# フェーズ6: ILP最適化（動的モード・デフォルト）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode dynamic

# または静的モード
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --optimization-mode static
```

**生成されるファイル**：
- `time_dependent_output/{query_set}/td_mv_optimization_result{suffix}.json`: 動的最適化結果
- `time_dependent_output/{query_set}/static_mv_optimization_result{suffix}.json`: 静的最適化結果
- `time_dependent_output/{query_set}/pruning_result{suffix}.json`: プルーニング結果（`--use-pruning`使用時）

**注**: `{suffix}` は `--exp-suffix` オプションで指定した値（例: `_16_2`）。省略時は空文字列。

#### CF Pruning（候補削減）オプション

大量のタイムステップ（20以上）を扱う場合、ILP最適化の計算時間が指数的に増加します。この問題を解決するため、**CF Pruning（Workload Summary Tree）**機能を使用できます。

**CF Pruningとは**:
- 論文Section 4.3で提案されている手法
- 全タイムステップを階層的な二分木として表現
- 各ノードで3タイムステップのみの小さなILPを解く
- 全ノードで選ばれたMVの和集合を「有望な候補」として抽出
- メイン最適化では有望な候補のみを使用（計算量を大幅削減）

**使用方法**:
```bash
# プルーニングを使用（推奨: タイムステップ数 >= 20）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job --use-pruning

# プルーニングなし（デフォルト: タイムステップ数 < 20）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 6 --query-set job
```

**プルーニング結果の確認**:
```bash
# プルーニング統計を確認
cat time_dependent_output/job/pruning_result.json
```

**出力例**:
```json
{
  "total_candidates": 1256,
  "promising_candidates": 320,
  "filtered_out": 936,
  "retention_rate": 0.255,
  "reduction_rate": 0.745,
  "promising_mv_names": ["node_123", "node_456", ...]
}
```

**パフォーマンス**:
- 5タイムステップ: プルーニングの効果は小さい（数秒の削減）
- 20タイムステップ: 数分の削減が期待できる
- 50タイムステップ: プルーニングなしでは実行不可能 → プルーニングで実行可能に

**技術詳細**:
- 新規ファイル: `core/workload_summary_tree.py`, `core/local_ilp_optimizer.py`, `core/cf_pruner.py`
- ツリーノード数: 約 `2T - 1`（Tはタイムステップ数）
- 各ノードの最適化: 3タイムステップのみ（高速）
- 境界制約: 親ノードの解を子ノードに伝搬（整合性を保証）

---

### ステップ7: MV作成SQL生成

最適化結果に基づいてMV作成SQLを生成します。モードに応じて異なるSQLが生成されます。

```bash
# フェーズ7: SQL生成（動的モード）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 7 --query-set job --optimization-mode dynamic

# または静的モード
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 7 --query-set job --optimization-mode static
```

**生成されるファイル**:
- **動的モード**: `time_dependent_output/{query_set}/timestep_*_{timestep_name}.sql` - 各タイムステップのマイグレーションSQL
- **静的モード**: `time_dependent_output/{query_set}/static_initial_mvs.sql` - 初期MV作成SQL

---

### ステップ8: クエリ書き換え

選択されたMVを使用してクエリを書き換えます。モードに応じて異なる書き換えが行われます。

```bash
# フェーズ8: クエリ書き換え（動的モード）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 8 --query-set job --optimization-mode dynamic

# または静的モード
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 8 --query-set job --optimization-mode static
```

**生成されるファイル**:
- **動的モード**: 
  - `time_dependent_output/{query_set}/jobs/timestep_0_*/`: タイムステップ0の書き換えクエリ
  - `time_dependent_output/{query_set}/jobs/timestep_1_*/`: タイムステップ1の書き換えクエリ
  - `time_dependent_output/{query_set}/jobs/timestep_2_*/`: タイムステップ2の書き換えクエリ
- **静的モード**:
  - `time_dependent_output/{query_set}/jobs/rewritten_static/`: 静的MV用書き換えクエリ

各フォルダには、全てのクエリ（113個）が書き換えられたSQLファイルとして保存されます。

---

### ステップ9: ベンチマーク実行

作成したMVと書き換えクエリを使用してベンチマークを実行し、性能を測定します。
**注意**: `--benchmark-mode` 引数を使用します（`--optimization-mode`ではありません）。

```bash
# フェーズ9: ベンチマーク実行（動的MVモード）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode dynamic

# または静的MVモード
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode static

# またはベースライン（MVなし）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 9 --query-set job --benchmark-mode baseline
```

**ベンチマークモード**:
- `dynamic`: 動的MV - 各タイムステップでマイグレーションを実行してMVを更新
- `static`: 静的MV - 最初のタイムステップのMVのみを作成し、全タイムステップで使用  
- `baseline`: ベースライン - MVを使用せず元のクエリを実行

**生成されるファイル**：
- `time_dependent_output/{query_set}/benchmark_results_{mode}{suffix}.json`: ベンチマーク結果
  - `{mode}`: `dynamic`, `static`, `baseline`
  - `{suffix}`: `--exp-suffix` オプションで指定した値（省略時は空文字列）

**ベンチマーク結果の内容**:
- 各タイムステップでの全クエリの実行時間（ミリ秒）
- タイムアウトしたクエリの情報
- MVの作成・削除にかかったマイグレーション時間
- タイムステップごとの総実行時間
- 全体のサマリー統計（総実行時間、平均クエリ時間など）

**実行時間の計測**:
- **クエリ実行時間**: 各クエリの実際の実行時間のみを計測
- **マイグレーション時間**: MVの作成・削除にかかった時間を別途計測
- **注意**: ベンチマーク実行時間には、最適化時間、SQL生成時間、クエリ書き換え時間は含まれません
### 全フェーズの一括実行

`--optimization-mode` を指定して全フェーズを実行します。

```bash
# 全フェーズを動的モードで実行（デフォルト）
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --query-set job --optimization-mode dynamic

# または静的モードで実行
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase all --query-set job --optimization-mode static
```

**注意**: 
- フェーズ6, 7, 8 では `--optimization-mode` (static/dynamic) を使用
- フェーズ9 では `--benchmark-mode` (static/dynamic/baseline) を使用
- `--phase all` 実行時は、指定した `--optimization-mode` がフェーズ6, 7, 8に適用されます

---

## 実験サフィックスの使い方

異なる頻度設定や周期の実験を同時に管理するため、`--exp-suffix` オプションでサフィックスを指定できます。

### 基本的な使い方

```bash
# 周期8の実験（16タイムステップ、周期8）
python experiments/small_test_ver2/scripts/run_experiment_normal.py \
  --phase all \
  --query-set job \
  --exp-suffix _16_2

# 周期4の実験（16タイムステップ、周期4）
python experiments/small_test_ver2/scripts/run_experiment_normal.py \
  --phase all \
  --query-set job \
  --exp-suffix _16_4
```

### 必要なファイル準備

サフィックスを使用する場合、対応する頻度ファイルを準備してください：

```bash
01_queries/job/
├── frequency_time_dependent.json          # デフォルト
├── frequency_time_dependent_16_2.json     # --exp-suffix _16_2 で使用
└── frequency_time_dependent_16_4.json     # --exp-suffix _16_4 で使用
```

### 生成されるファイル

サフィックスは以下のファイル名に適用されます：

```bash
time_dependent_output/job/
├── td_mv_optimization_result.json              # デフォルト
├── td_mv_optimization_result_16_2.json         # _16_2 の最適化結果
├── td_mv_optimization_result_16_4.json         # _16_4 の最適化結果
├── pruning_result_16_2.json                    # プルーニング結果
├── benchmark_results_dynamic_16_2.json         # ベンチマーク結果
└── benchmark_results_dynamic_16_4.json
```

### 個別フェーズでの使用

```bash
# Phase 6のみ実行（最適化結果にサフィックス付加）
python experiments/small_test_ver2/scripts/run_experiment_normal.py \
  --phase 6 \
  --query-set job \
  --exp-suffix _16_2

# Phase 7実行（サフィックス付き最適化結果を読み込む）
python experiments/small_test_ver2/scripts/run_experiment_normal.py \
  --phase 7 \
  --query-set job \
  --exp-suffix _16_2
```

**注意**: Phase 7とPhase 8は、サフィックス付きの最適化結果を読み込みますが、出力ファイル（SQLや書き換えクエリ）にはサフィックスは付きません（最後に実行した最適化結果で上書きされます）。

---


### 最適化以降の一括実行 (Post-Optimization)

Phase 6（最適化）から Phase 9（ベンチマーク）までを一括実行します。
コスト見積もり修正後の再最適化や、Static/Dynamicモードの比較に便利です。

```bash
# 最適化以降を動的モードで実行
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase post-opt --query-set job --optimization-mode dynamic

# または静的モードで実行
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase post-opt --query-set job --optimization-mode static
```

**実行されるフェーズ**:
- Phase 6: MV最適化
- Phase 7: MV生成SQL作成
- Phase 8: クエリ書き換え
- Phase 9: ベンチマーク実行

---

## 入力ファイル

時間依存最適化に必要な入力ファイルは以下の通りです：

### 必須の入力データ
1. **クエリ定義**:
   - `01_queries/{query_set}/query1.sql` 〜 `query9.sql`: 最適化対象のSQLクエリ
   - `{query_set}` は `job_like` または `explicit_join` など

2. **クエリパーサの出力**:
   - `03_parsed/{query_set}/qp_class.pkl`: MV候補の効用行列 u_ij、包含関係 X、ストレージサイズ b_j などを含む

3. **クエリ頻度設定**：
   - `01_queries/{query_set}/frequency_time_dependent{suffix}.json`: 各タイムステップでの各クエリの実行頻度
   - `{suffix}` は `--exp-suffix` で指定（省略時は空文字列）

4. **マイグレーションコスト**:
   - `04_migration/{query_set}/migration_costs.json`: 各MV候補の作成レシピとコスト

### 設定ファイル
- `config.yaml`: 実験環境の設定（データベース接続情報など）

---

## ディレクトリ構造

```
experiments/small_test_ver2/
├── core/                          # コア機能（必須）
│   ├── time_dependent_optimizer.py    # ILP最適化クラス
│   ├── workload_summary_tree.py       # Workload Summary Tree（プルーニング用）
│   ├── local_ilp_optimizer.py         # Local ILP最適化（プルーニング用）
│   ├── cf_pruner.py                   # CF Prunerクラス（プルーニング本体）
│   ├── io_loaders.py                  # データロード
│   └── small_test_schema_provider.py  # スキーマプロバイダー
├── migration/                     # マイグレーション関連
│   ├── enumerate_simple_migration_plan.py  # シンプルプラン列挙
│   └── simple_migration_cost_calculator.py # コスト計算
├── mv_generation/                 # MV生成関連
│   ├── enhanced_mv_generator.py       # 拡張MVジェネレーター
│   ├── simple_mv_sql_generator.py     # シンプルSQLジェネレーター
│   └── comma_join_rewriter.py         # カンマ結合書き換え
├── scripts/                       # 実行スクリプト
│   ├── run_experiment_normal.py       # メイン実験スクリプト（全フェーズ統合）
│   ├── run_time_dependent_with_migration.py  # 旧時間依存最適化（非推奨）
│   └── setup_imdb.py                  # IMDBセットアップ
├── utils/                         # ユーティリティ
│   └── inspect_pickle.py              # デバッグ用
├── 01_queries/                    # クエリ定義
│   ├── job/                           # JOBクエリセット
│   │   ├── *.sql                      # クエリファイル
│   │   └── frequency_time_dependent.json  # 時間依存頻度
│   └── job_like/                      # 旧クエリセット（非推奨）
├── 02_json/                       # EXPLAIN出力
│   └── job/                           # JOBクエリセットのEXPLAIN結果（ノードID付き）
├── 03_parsed/                     # パース結果
│   └── job/
│       ├── qp_class.pkl               # クエリパーサ出力
│       └── parse_summary.json         # パースサマリー
├── 04_migration/                  # マイグレーション計画とコスト
│   └── job/
│       ├── simple_migration_plans.json    # マイグレーションプラン（SQL）
│       ├── simple_migration_costs.json    # マイグレーションコスト
│       └── partial_explain_*.json         # 部分EXPLAIN（中間データ）
├── time_dependent_output/         # 時間依存最適化出力
│   └── job/
│       ├── td_mv_optimization_result.json # 最適化結果
│       ├── timestep_*_*.sql               # タイムステップごとのマイグレーションSQL
│       └── jobs/                          # 書き換えクエリ
│           ├── timestep_0_0/              # タイムステップ0の書き換えクエリ
│           ├── timestep_1_1/              # タイムステップ1の書き換えクエリ
│           └── timestep_2_2/              # タイムステップ2の書き換えクエリ
├── small_docs/                    # ドキュメント
├── 00_setup.sql
├── insert_queries.sql
├── config.yaml
└── README.md
```

---

## 実行スクリプトと関連ファイル

### コアスクリプト（実行に必須）
| ファイル名 | 場所 | 役割 |
|-----------|------|------|
| `run_experiment_normal.py` | `scripts/` | メイン実験スクリプト（全フェーズ統合）<br>- フェーズ1: EXPLAIN JSON生成<br>- フェーズ2: クエリパース<br>- フェーズ3: JSONノードID付加<br>- フェーズ4: マイグレーションプラン列挙<br>- フェーズ5: マイグレーションコスト計算<br>- フェーズ6: ILP最適化<br>- フェーズ7: マイグレーションSQL生成<br>- フェーズ8: クエリ書き換え<br>- フェーズ9: ベンチマーク実行 |
| `enumerate_simple_migration_plan.py` | `migration/` | マイグレーションプラン（SQL）の列挙（フェーズ2.7から内部利用） |
| `simple_migration_cost_calculator.py` | `migration/` | マイグレーションコストの測定（フェーズ2.8から内部利用） |

### サポートスクリプト
| ファイル名 | 場所 | 役割 |
|-----------|------|------|
| `run_time_dependent_with_migration.py` | `scripts/` | 旧時間依存最適化スクリプト（非推奨、後方互換性のため残存） |
| `setup_imdb.py` | `scripts/` | IMDBデータベースのセットアップツール |

### 最適化・パースクラス
| ファイル名 | 場所 | 役割 |
|-----------|------|------|
| `time_dependent_optimizer.py` | `core/` | 時間依存ILP最適化クラス（変数・制約・目的関数の定義） |
| `workload_summary_tree.py` | `core/` | Workload Summary Tree（プルーニング用二分木構造） |
| `local_ilp_optimizer.py` | `core/` | Local ILP最適化（3タイムステップ限定、プルーニング用） |
| `cf_pruner.py` | `core/` | CF Prunerクラス（候補削減アルゴリズムの実装） |
| `io_loaders.py` | `core/` | データロードユーティリティ（pickle/JSONの読み込み） |
| `small_test_schema_provider.py` | `core/` | スキーマ情報プロバイダー |

### MV生成関連
| ファイル名 | 場所 | 役割 |
|-----------|------|------|
| `enhanced_mv_generator.py` | `mv_generation/` | 拡張MVジェネレーター |
| `simple_mv_sql_generator.py` | `mv_generation/` | シンプルSQLジェネレーター |
| `comma_join_rewriter.py` | `mv_generation/` | カンマ結合書き換え |

### クエリ書き換え
| ファイル名 | 場所 | 役割 |
|-----------|------|------|
| `query_rewriter.py` | `rewrite/` | クエリリライター |

### ユーティリティ
| ファイル名 | 場所 | 役割 |
|-----------|------|------|
| `inspect_pickle.py` | `utils/` | pickleファイルの内容確認用 |

### データベース関連
| ファイル名 | 役割 |
|-----------|------|
| `00_setup.sql` | データベーススキーマのセットアップSQL |
| `insert_queries.sql` | テストデータの挿入SQL |

---

## 出力ファイル

最適化実行後に生成されるファイル：

### 主要な出力
- `time_dependent_output/{query_set}/td_mv_optimization_result.json`: 
  - 最適化結果の全情報
  - 各タイムステップで選択されたMV
  - ワークロードコスト、マイグレーションコストの内訳
  - 入力データ（b_j, u_ij, X, 頻度など）

### 中間出力
- `03_parsed/{query_set}/qp_class.pkl`: クエリパーサの出力
- `04_migration/{query_set}/migration_plans.json`: マイグレーションプラン
- `04_migration/{query_set}/migration_costs.json`: マイグレーションコスト
- `02_json/{query_set}/query*.json`: EXPLAIN JSON
- `03_parsed/{query_set}/parse_summary.json`: パース結果サマリー

### 分析結果（オプション）
- `time_dependent_output/store_result/`: 複数シナリオの結果を保存するディレクトリ
- `time_dependent_output/store_result/analysis_by_budget_and_freq.md`: 容量と頻度による比較分析レポート

---

## 結果の確認

最適化結果は `time_dependent_output/{query_set}/td_mv_optimization_result.json` に保存されます。主要な情報は以下の通りです：

```json
{
  "objective": -1234.56,           // 総目的関数値（小さいほど良い）
  "workload_cost": -1290.12,       // ワークロード利得（負値＝利得）
  "migration_cost": 55.56,         // マイグレーションコスト
  "solve_time_sec": 12.34,         // 求解時間
  "z_by_timestep": [...],          // 各時刻でのMV選択（1=選択, 0=非選択）
  "y_by_timestep": [...],          // 各時刻での利用関係
  "migration_analysis": [...],     // マイグレーション詳細分析
  "summary": {
    "total_mvs_created": 10,
    "total_mvs_deleted": 3,
    "avg_mvs_per_timestep": 7.5,
    "avg_storage_utilization": 85.2
  },
  "input_data": {                  // 入力データの記録
    "storage_budget": 10240,
    "mv_storage_sizes": {...},
    "query_frequencies": {...},
    "utility_matrix": {...},
    "inclusion_matrix": {...}
  }
}
```

---

## トラブルシューティング

### Gurobiライセンスエラー
- Gurobiの有効なライセンスが必要です
- 無料版は変数数に制限があります（2000変数まで）
- 学術ライセンスまたは商用ライセンスを取得してください

### pickleファイルが見つからない
- ステップ2（クエリパース）が正常に完了していることを確認してください
- `03_parsed/{query_set}/qp_class.pkl` が存在することを確認してください
- `--query-set` オプションで正しいクエリセットを指定していることを確認してください

### マイグレーションコストが計算されない
- データベースが起動していることを確認してください
- ステップ3（マイグレーションプラン列挙）が完了していることを確認してください
- `04_migration/{query_set}/migration_plans.json` が存在することを確認してください
- 各ステップで同じ `--query-set` オプションを使用していることを確認してください

---

## 実験設定のカスタマイズ

### ストレージ予算の変更
`scripts/run_time_dependent_with_migration.py` の以下の行を編集：
```python
B_max = float(102400)  # バイト単位（例: 100KB）
```

### クエリ頻度の変更
`01_queries/{query_set}/frequency_time_dependent.json` を編集して、各タイムステップでの頻度を調整します。

### タイムステップの追加
`01_queries/{query_set}/frequency_time_dependent.json` に新しいタイムステップを追加します。

### 新しいクエリセットの追加
1. `01_queries/` に新しいフォルダを作成（例: `new_queries/`）
2. SQLクエリファイル（`query1.sql` 〜 `queryN.sql`）を配置
3. `frequency_time_dependent.json` を作成
4. すべてのステップで `--query-set new_queries` を指定して実行

---

## 不要なファイル一覧

以下のファイルは時間依存最適化の実行には不要です（削除しても実行に影響しません）：

### 実行後に生成される出力ファイル
- `time_dependent_output/{query_set}/td_mv_optimization_result.json`
- `time_dependent_output/{query_set}/*.json`（その他の出力）
- `04_migration/{query_set}/migration_plans.json`（実行後に再生成可能）
- `04_migration/{query_set}/migration_costs.json`（実行後に再生成可能）
- `02_json/{query_set}/query*.json`（実行後に再生成可能）
- `03_parsed/{query_set}/qp_class.pkl`（実行後に再生成可能）
- `03_parsed/{query_set}/parse_summary.json`（実行後に再生成可能）

### ドキュメント・計画ファイル
- `small_docs/`（ドキュメントのみ、実行には不要）
- `README_old.md`（旧README）

### その他
- `05_mv_sql/`（別実験の出力）
- `06_rewritten/`（別実験の出力）
- `gurobi.lic`（ライセンスファイル、インストール時に別途配置）
- `__pycache__/`（Pythonキャッシュ）

### 明示的に除外されたディレクトリ
- `tool/`（ツール類、本実験には不要）
- `garvage_can/`（ゴミ箱、不要ファイルの保管場所）

---

## 参考

- ILP定式化の詳細: `small_docs/explain/time_dependent_optimizer.md`
- プロジェクト全体の概要: プロジェクトルートの `docs/` ディレクトリ


PostgreSQL で **現在データベース内にある実体化ビュー (Materialized Views)** の **サイズ一覧と合計サイズ** を確認するには、`pg_class` / `pg_namespace` / `pg_matviews` と `pg_total_relation_size()` を組み合わせて取得できます。

---

# ✅ **実体化ビューのサイズ一覧（個別）を取得する SQL**

```sql
SELECT
    matviewname AS mv_name,
    pg_size_pretty(pg_total_relation_size(pg_class.oid)) AS total_size,
    pg_total_relation_size(pg_class.oid) AS total_size_bytes
FROM pg_matviews
JOIN pg_class ON pg_class.relname = pg_matviews.matviewname
JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
WHERE pg_class.relkind = 'm'
ORDER BY pg_total_relation_size(pg_class.oid) DESC;
```

---

# ✅ **実体化ビューの合計サイズを取得する SQL**

```sql
SELECT
    pg_size_pretty(SUM(pg_total_relation_size(pg_class.oid))) AS total_mv_size,
    SUM(pg_total_relation_size(pg_class.oid)) AS total_mv_size_bytes
FROM pg_matviews
JOIN pg_class ON pg_class.relname = pg_matviews.matviewname
JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
WHERE pg_class.relkind = 'm';
```

---

# 📌 補足

* `pg_matviews` は materialized view 一覧が入っているシステムカタログ
* `pg_total_relation_size(oid)` は **テーブル / MV の本体 + インデックス + TOAST を含む総サイズ**
* `pg_size_pretty()` は読みやすい形式（MB / GB）に変換

---

全ての実体化ビューのサイズの合計は焼く70GB
