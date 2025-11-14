# Small Test Ver2 ディレクトリ構造整理ガイド

## 整理の目的
コードの可読性と保守性を向上させるため、`small_test_ver2` ディレクトリ内のファイルを機能ごとに分類・整理しました。

## 新しいディレクトリ構造

```
experiments/small_test_ver2/
├── core/                          # コア機能（ILP最適化とデータロード）
│   ├── __init__.py
│   ├── time_dependent_optimizer.py    # ILP最適化クラス
│   ├── io_loaders.py                  # データロードユーティリティ
│   └── small_test_schema_provider.py  # スキーマ情報プロバイダー
│
├── migration/                     # マイグレーション関連
│   ├── __init__.py
│   ├── enumerate_migration_plan.py    # マイグレーションプラン列挙
│   └── migration_cost_calculator.py   # コスト計算
│
├── mv_generation/                 # MV SQL生成関連
│   ├── __init__.py
│   ├── enhanced_mv_generator.py       # 拡張MVジェネレーター
│   ├── simple_mv_sql_generator.py     # シンプルSQLジェネレーター
│   └── comma_join_rewriter.py         # カンマ結合書き換え
│
├── rewrite/                       # クエリ書き換え
│   ├── __init__.py
│   └── query_rewriter.py              # クエリリライター
│
├── scripts/                       # 実行スクリプト
│   ├── __init__.py
│   ├── run_experiment_normal.py       # 通常実験実行
│   └── run_time_dependent_with_migration.py  # 時間依存最適化実行
│
├── utils/                         # ユーティリティ
│   ├── __init__.py
│   └── inspect_pickle.py              # デバッグ用ツール
│
├── 01_queries/                    # クエリ定義（SQL + 頻度設定）
├── 02_json/                       # EXPLAIN JSON出力
├── 03_parsed/                     # パース結果
├── time_dependent_output/         # 最適化結果出力
├── small_docs/                    # ドキュメント
├── tool/                          # 開発ツール（実験実行には不要）
├── garvage_can/                   # 未使用ファイル保管
│
├── 00_setup.sql                   # DBセットアップSQL
├── insert_queries.sql             # テストデータ挿入SQL
├── config.yaml                    # 実験設定
├── gurobi.lic                     # Gurobiライセンス
└── README.md                      # メインREADME
```

## 各ディレクトリの役割

### `core/` - コア機能
時間依存最適化の中核となる機能：
- **time_dependent_optimizer.py**: Gurobi を用いた ILP 最適化
- **io_loaders.py**: pickle/JSON からのデータ読み込み
- **small_test_schema_provider.py**: スキーマ情報の提供

### `migration/` - マイグレーション
MV のマイグレーションプラン生成とコスト計算：
- **enumerate_migration_plan.py**: 各 MV の作成レシピを列挙
- **migration_cost_calculator.py**: 各レシピの実行コストを測定

### `mv_generation/` - MV SQL生成
既存 MV を活用した新しい MV の SQL 生成：
- **enhanced_mv_generator.py**: MV 候補の抽出
- **simple_mv_sql_generator.py**: SQL 生成のメインクラス
- **comma_join_rewriter.py**: カンマ結合の書き換え処理

### `rewrite/` - クエリ書き換え
選択された MV を使ってクエリを書き換え：
- **query_rewriter.py**: クエリリライター

### `scripts/` - 実行スクリプト
実験を実行するメインスクリプト：
- **run_experiment_normal.py**: 段階的実験実行（setup → explain → parse → optimize）
- **run_time_dependent_with_migration.py**: 時間依存最適化の実行

### `utils/` - ユーティリティ
デバッグや開発支援ツール：
- **inspect_pickle.py**: pickle ファイルの内容確認

## インポートパスの変更

整理に伴い、インポートパスが変更されました：

### Before（整理前）
```python
from time_dependent_optimizer import TimeDependentOptimizer
from io_loaders import load_qp_inputs
from enumerate_migration_plan import GetMigrationPlans
```

### After（整理後）
```python
from experiments.small_test_ver2.core.time_dependent_optimizer import TimeDependentOptimizer
from experiments.small_test_ver2.core.io_loaders import load_qp_inputs
from experiments.small_test_ver2.migration.enumerate_migration_plan import GetMigrationPlans
```

または、`__init__.py` を通じて：
```python
from experiments.small_test_ver2.core import TimeDependentOptimizer, load_qp_inputs
from experiments.small_test_ver2.migration import GetMigrationPlans
```

## 実行コマンドの変更

整理に伴い、実行コマンドのパスが変更されました：

### Before（整理前）
```bash
python experiments/small_test_ver2/run_experiment_normal.py --phase 0
python experiments/small_test_ver2/enumerate_migration_plan.py
python experiments/small_test_ver2/migration_cost_calculator.py
python experiments/small_test_ver2/run_time_dependent_with_migration.py
```

### After（整理後）
```bash
python experiments/small_test_ver2/scripts/run_experiment_normal.py --phase 0
python experiments/small_test_ver2/migration/enumerate_migration_plan.py
python experiments/small_test_ver2/migration/migration_cost_calculator.py
python experiments/small_test_ver2/scripts/run_time_dependent_with_migration.py
```

## 移行手順

既存のスクリプトや設定ファイルがある場合：

1. **バックアップを作成**
   ```bash
   # 既存の作業ディレクトリをバックアップ
   cp -r experiments/small_test_ver2 experiments/small_test_ver2_backup
   ```

2. **新しいパスで実行**
   - README.md に記載された新しいパスでスクリプトを実行してください

3. **カスタムスクリプトの更新**
   - 独自のスクリプトがある場合、インポートパスを上記の「After」形式に更新してください

## メリット

1. **可読性の向上**: 機能ごとにファイルが整理され、目的のファイルを見つけやすくなりました
2. **保守性の向上**: 関連するファイルがまとまっており、変更箇所を特定しやすくなりました
3. **拡張性の向上**: 新しい機能を追加する際に、適切なディレクトリに配置できます
4. **名前空間の明確化**: `__init__.py` により、モジュールとしての構造が明確になりました

## トラブルシューティング

### ImportError が発生する場合
- プロジェクトルートからの相対パスでインポートしていることを確認してください
- `sys.path` にプロジェクトルートが追加されていることを確認してください

### ファイルが見つからない場合
- 実行コマンドのパスが新しい構造に対応しているか確認してください
- README.md に記載されたパスを参照してください

## 参考

- メイン README: `experiments/small_test_ver2/README.md`
- ILP 定式化: `experiments/small_test_ver2/small_docs/explain/time_dependent_optimizer.md`
