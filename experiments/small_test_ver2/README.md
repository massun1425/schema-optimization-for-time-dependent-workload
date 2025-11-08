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

## 実行手順

### 前提条件
- Python 3.x がインストールされていること
- Gurobi がインストールされており、ライセンスが有効であること
- 必要なPythonパッケージがインストールされていること（`requirements.txt` を参照）

### ステップ1: データベースのセットアップとクエリ実行計画の取得

まず、データベースをセットアップし、各クエリの実行計画（EXPLAIN JSON）を取得します。

```bash
# フェーズ0: データベースのセットアップ
python experiments/small_test_ver2/run_experiment_normal.py --phase 0
```

```bash
# フェーズ1: クエリのEXPLAIN JSON生成
python experiments/small_test_ver2/run_experiment_normal.py --phase 1
```

**生成されるファイル**:
- `02_json/query1.json` 〜 `query9.json`: 各クエリのEXPLAIN結果

---

### ステップ2: クエリパース（MV候補の抽出と効用計算）

EXPLAIN結果を解析し、MV候補とその効用を計算します。

```bash
# フェーズ2: クエリパース
python experiments/small_test_ver2/run_experiment_normal.py --phase 2
```

**生成されるファイル**:
- `time_dependent_output/qp_class.pkl`: クエリパーサの出力（u_ij, X, b_j, node_list などを含む）
- `time_dependent_output/qp_class.json`: 同上（JSON形式、ただし X は含まれない）
- `03_parsed/query1_parsed.json` 〜 `query9_parsed.json`: 各クエリの解析結果

---

### ステップ3: マイグレーションプランの列挙

各MV候補について、作成に必要な依存関係とマイグレーションプラン（SQLレシピ）を列挙します。

```bash
python experiments/small_test_ver2/enumerate_migration_plan.py
```

**生成されるファイル**:
- `time_dependent_output/migration_plan/migration_plans.json`: 全MV候補のマイグレーションプラン（SQL）

---

### ステップ4: マイグレーションコストの計算

各マイグレーションプランを実際に実行し、コストを測定します。

```bash
python experiments/small_test_ver2/migration_cost_calculator.py
```

**生成されるファイル**:
- `time_dependent_output/migration_plan/migration_costs.json`: 各MV候補のレシピとコスト

---

### ステップ5: 時間依存最適化の実行

タイムステップごとのクエリ頻度とマイグレーションコストを考慮して、ILP最適化を実行します。

```bash
python experiments/small_test_ver2/run_time_dependent_with_migration.py
```

**生成されるファイル**:
- `time_dependent_output/td_mv_optimization_result.json`: 最適化結果（選択されたMV、コスト、マイグレーション分析など）

---

## 入力ファイル

時間依存最適化に必要な入力ファイルは以下の通りです：

### 必須の入力データ
1. **クエリ定義**:
   - `01_queries/query1.sql` 〜 `query9.sql`: 最適化対象のSQLクエリ

2. **クエリパーサの出力**:
   - `time_dependent_output/qp_class.pkl`: MV候補の効用行列 u_ij、包含関係 X、ストレージサイズ b_j などを含む

3. **クエリ頻度設定**:
   - `01_queries/frequency_time_dependent.json`: 各タイムステップでの各クエリの実行頻度

4. **マイグレーションコスト**:
   - `time_dependent_output/migration_plan/migration_costs.json`: 各MV候補の作成レシピとコスト

### 設定ファイル
- `config.yaml`: 実験環境の設定（データベース接続情報など）

---

## 実行スクリプトと関連ファイル

### コアスクリプト（実行に必須）
| ファイル名 | 役割 |
|-----------|------|
| `run_experiment_normal.py` | データベースセットアップ、EXPLAIN取得、クエリパース |
| `enumerate_migration_plan.py` | マイグレーションプラン（SQL）の列挙 |
| `migration_cost_calculator.py` | マイグレーションコストの測定 |
| `run_time_dependent_with_migration.py` | 時間依存最適化のメイン実行スクリプト |

### 最適化・パースクラス
| ファイル名 | 役割 |
|-----------|------|
| `time_dependent_optimizer.py` | 時間依存ILP最適化クラス（変数・制約・目的関数の定義） |
| `io_loaders.py` | データロードユーティリティ（pickle/JSONの読み込み） |
| `time_dependent_parser.py` | 時間依存ワークロード用のクエリパーサ |
| `frequency_weighted_parser.py` | 頻度重み付きクエリパーサ |
| `small_test_schema_provider.py` | スキーマ情報プロバイダー |

### 補助スクリプト
| ファイル名 | 役割 |
|-----------|------|
| `migration_planner.py` | マイグレーションプランの生成ロジック |
| `inspect_pickle.py` | pickleファイルの内容確認用 |

### データベース関連
| ファイル名 | 役割 |
|-----------|------|
| `00_setup.sql` | データベーススキーマのセットアップSQL |
| `insert_queries.sql` | テストデータの挿入SQL |

---

## 出力ファイル

最適化実行後に生成されるファイル：

### 主要な出力
- `time_dependent_output/td_mv_optimization_result.json`: 
  - 最適化結果の全情報
  - 各タイムステップで選択されたMV
  - ワークロードコスト、マイグレーションコストの内訳
  - 入力データ（b_j, u_ij, X, 頻度など）

### 中間出力
- `time_dependent_output/qp_class.pkl`: クエリパーサの出力
- `time_dependent_output/migration_plan/migration_costs.json`: マイグレーションコスト
- `02_json/query*.json`: EXPLAIN JSON
- `03_parsed/query*_parsed.json`: パース結果

### 分析結果（オプション）
- `time_dependent_output/store_result/`: 複数シナリオの結果を保存するディレクトリ
- `time_dependent_output/store_result/analysis_by_budget_and_freq.md`: 容量と頻度による比較分析レポート

---

## 結果の確認

最適化結果は `time_dependent_output/td_mv_optimization_result.json` に保存されます。主要な情報は以下の通りです：

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
- `time_dependent_output/qp_class.pkl` が存在することを確認してください

### マイグレーションコストが計算されない
- データベースが起動していることを確認してください
- ステップ3（マイグレーションプラン列挙）が完了していることを確認してください

---

## 実験設定のカスタマイズ

### ストレージ予算の変更
`run_time_dependent_with_migration.py` の以下の行を編集：
```python
B_max = float(102400)  # バイト単位（例: 100KB）
```

### クエリ頻度の変更
`01_queries/frequency_time_dependent.json` を編集して、各タイムステップでの頻度を調整します。

### タイムステップの追加
`01_queries/frequency_time_dependent.json` に新しいタイムステップを追加します。

---

## 不要なファイル一覧

以下のファイルは時間依存最適化の実行には不要です（削除しても実行に影響しません）：

### 実行後に生成される出力ファイル
- `time_dependent_output/td_mv_optimization_result.json`
- `time_dependent_output/store_result/*.json`
- `time_dependent_output/normal_summary.json`
- `time_dependent_output/migration_plan.json`
- `time_dependent_output/analyze_all_mvs.sql`
- `time_dependent_output/morning_to_evening.sql`
- `02_json/query*.json`（実行後に再生成可能）
- `03_parsed/query*_parsed.json`（実行後に再生成可能）

### 使用されない補助スクリプト
- `run_experiment_time_dependent.py`（旧版、現在は run_time_dependent_with_migration.py を使用）
- `comma_join_rewriter.py`（別機能）
- `enhanced_mv_generator.py`（別機能）
- `mv_creator.py`（別機能）
- `mv_sql_generator.py`（別機能）
- `simple_mv_sql_generator.py`（別機能）
- `query_rewriter.py`（別機能）
- `inspect_pickle.py`（デバッグ用、実行には不要）

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
