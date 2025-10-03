# リファクタリング進捗チェックリスト

最終更新: 2025年10月3日

## 📊 全体進捗

- [ ] Phase 0: 準備・環境整備 (0%)
- [ ] Phase 1: 設定管理の外部化 (0%)
- [ ] Phase 2: ユーティリティモジュール整理 (0%)
- [ ] Phase 3: QueryManager リファクタリング (0%)
- [ ] Phase 4: QueryParser リファクタリング (0%)
- [ ] Phase 5: ILP最適化モジュール統合 (0%)
- [ ] Phase 6: クエリ書き換えモジュール (0%)
- [ ] Phase 7: 実験スクリプト整理 (0%)
- [ ] Phase 8: テストコード追加 (0%)
- [ ] Phase 9: 最終調整とドキュメント (0%)

---

## Phase 0: 準備・環境整備

### タスク
- [ ] バックアップブランチ作成
- [ ] ディレクトリ構造作成
  - [ ] src/ とサブディレクトリ
  - [ ] config/, scripts/, tests/
  - [ ] __init__.py ファイル
- [ ] 開発ツールインストール
  - [ ] mypy
  - [ ] black, ruff
  - [ ] pytest
  - [ ] pyyaml
- [ ] 設定ファイル作成
  - [ ] pyproject.toml
  - [ ] setup.py
  - [ ] .gitignore 更新
  - [ ] .env.example
- [ ] 動作確認
- [ ] Git コミット

### 検証
- [ ] `import src` が成功
- [ ] 開発ツールが動作
- [ ] `pip install -e .` が成功

---

## Phase 1: 設定管理の外部化

### タスク
- [ ] YAML設定ファイル作成
  - [ ] config/default.yaml
  - [ ] config/experiments/job_benchmark.yaml
  - [ ] config/experiments/ceb_benchmark.yaml
- [ ] 設定管理クラス実装
  - [ ] config/settings.py
  - [ ] データクラス定義
  - [ ] YAML読み込み
  - [ ] 環境変数オーバーライド
  - [ ] 後方互換性プロパティ
- [ ] レガシーユーティリティ移行
  - [ ] src/utils/legacy.py
- [ ] テスト作成
  - [ ] tests/unit/test_settings.py
- [ ] Git コミット

### 検証
- [ ] 設定ファイルが読み込める
- [ ] 環境変数オーバーライドが動作
- [ ] テストが通る
- [ ] settings.GET_CEB が動作

---

## Phase 2: ユーティリティモジュール整理

### タスク
- [ ] ファイル操作ユーティリティ
  - [ ] src/utils/file_utils.py
- [ ] ロギングユーティリティ
  - [ ] src/utils/logging_utils.py
  - [ ] 統一ロガー作成
- [ ] ソートユーティリティ
  - [ ] src/utils/sorting.py
- [ ] テスト作成
  - [ ] tests/unit/test_file_utils.py
  - [ ] tests/unit/test_logging.py
- [ ] 既存コードの移行開始
- [ ] Git コミット

### 検証
- [ ] ユーティリティがインポート可能
- [ ] ロガーが動作
- [ ] テストが通る

---

## Phase 3: QueryManager リファクタリング

### タスク
- [ ] データモデル定義
  - [ ] src/core/models.py
  - [ ] QueryNode, LeafNode, NonLeafNode
- [ ] QueryManager 実装
  - [ ] src/core/query_manager.py
  - [ ] 型ヒント追加
  - [ ] docstring 追加
  - [ ] メソッド整理
- [ ] テスト作成
  - [ ] tests/unit/test_query_manager.py
- [ ] 既存コードとの互換性確保
- [ ] Git コミット

### 検証
- [ ] QueryManager が動作
- [ ] 既存の query_parse_beta.py から移行
- [ ] テストが通る

---

## Phase 4: QueryParser リファクタリング

### タスク
- [ ] QueryParser 実装
  - [ ] src/core/query_parser.py
  - [ ] ILP依存の削除
  - [ ] 型ヒント追加
  - [ ] docstring 追加
- [ ] テスト作成
  - [ ] tests/unit/test_query_parser.py
- [ ] 統合テスト
  - [ ] tests/integration/test_query_parsing.py
- [ ] Git コミット

### 検証
- [ ] QueryParser が動作
- [ ] 循環依存が解消
- [ ] テストが通る
- [ ] 既存機能が動作

---

## Phase 5: ILP最適化モジュール統合

### タスク
- [ ] 基底クラス実装
  - [ ] src/optimization/base.py
  - [ ] BaseILPOptimizer
- [ ] 各アルゴリズム実装
  - [ ] src/optimization/normal.py
  - [ ] src/optimization/bigsubs.py
  - [ ] src/optimization/utility_capacity.py
  - [ ] src/optimization/utility.py
  - [ ] src/optimization/frequency.py
- [ ] Factory実装
  - [ ] src/optimization/factory.py
- [ ] テスト作成
  - [ ] tests/unit/test_optimization.py
- [ ] Git コミット

### 検証
- [ ] すべてのILPアルゴリズムが動作
- [ ] Factoryパターンが動作
- [ ] テストが通る
- [ ] コードの重複が削減

---

## Phase 6: クエリ書き換えモジュール

### タスク
- [ ] QueryRewriter 実装
  - [ ] src/rewrite/query_rewriter.py
- [ ] MVGenerator 実装
  - [ ] src/rewrite/mv_generator.py
- [ ] SQLパーサー実装
  - [ ] src/rewrite/sql_parser.py
- [ ] テスト作成
  - [ ] tests/unit/test_rewriter.py
- [ ] Git コミット

### 検証
- [ ] クエリ書き換えが動作
- [ ] MV生成が動作
- [ ] テストが通る

---

## Phase 7: 実験スクリプト整理

### タスク
- [ ] メインスクリプト実装
  - [ ] scripts/run_experiment.py
  - [ ] CLI化（Click使用）
- [ ] 最適化スクリプト
  - [ ] scripts/run_optimization.py
- [ ] セットアップスクリプト
  - [ ] scripts/setup_database.py
- [ ] Git コミット

### 検証
- [ ] CLIが動作
- [ ] 実験が実行可能
- [ ] 既存のワークフローが動作

---

## Phase 8: テストコード追加

### タスク
- [ ] ユニットテスト拡充
  - [ ] カバレッジ 50%以上
- [ ] 統合テスト作成
  - [ ] tests/integration/test_experiment_flow.py
- [ ] フィクスチャ作成
  - [ ] tests/fixtures/
- [ ] pytest設定
  - [ ] tests/conftest.py
- [ ] Git コミット

### 検証
- [ ] カバレッジ 50%以上
- [ ] すべてのテストが通る
- [ ] CI/CDが通る（将来）

---

## Phase 9: 最終調整とドキュメント

### タスク
- [ ] README.md 更新
- [ ] APIドキュメント作成
- [ ] コードフォーマット
  - [ ] black . 実行
  - [ ] ruff check 実行
- [ ] 型チェック
  - [ ] mypy src/ 実行
- [ ] 不要ファイルの削除/移動
- [ ] Git コミット
- [ ] プルリクエスト作成

### 検証
- [ ] すべてのチェックが通る
- [ ] ドキュメントが最新
- [ ] 動作確認完了

---

## 🎯 最終確認

### コード品質
- [ ] mypy --strict でエラーなし（または最小限）
- [ ] black でフォーマット済み
- [ ] ruff でリントエラーなし
- [ ] テストカバレッジ 50%以上

### 機能
- [ ] すべてのILPアルゴリズムが動作
- [ ] 実験が実行可能
- [ ] 設定ファイルで制御可能

### ドキュメント
- [ ] README.md が最新
- [ ] すべてのパブリック関数にdocstring
- [ ] API文ドキュメント存在

### Git
- [ ] すべての変更がコミット済み
- [ ] コミットメッセージが明確
- [ ] プルリクエスト準備完了

---

## 📊 統計

- **総フェーズ数**: 10
- **完了フェーズ**: 0
- **進捗率**: 0%
- **推定残り時間**: 6-8週間

---

## 📝 メモ

### 変更履歴
- 2025-10-03: 初版作成

### 課題・注意事項
- （ここに気づいた課題を記録）

### 次のアクション
1. Phase 0 を開始
2. 各フェーズ完了後にこのファイルを更新
