# 未使用コードの判定（2026-09-29）

TODO の「5. 未使用のコードと古いスクリプトを archive へ移す」のための調査結果。**ファイルの移動・変更はまだしていない。**

> **追記（2026-09-29）**: DeepDB・NeuroCard は使わないので削除した。
> - コード: `migration/{deepdb_estimator,deepdb_migration_cost_calculator,neurocard_migration_cost_calculator}.py` と `src/estimation/`（4 ファイル）を `git rm`。`run_experiment_normal.py` から `--use-deepdb`・`--use-neurocard`・`--compare`（DeepDB 専用）と Phase 5 の分岐を削除
> - `archive/` の `deepdb_full`・`deepdb_light`・`neurocard_full`・`neurocard_light`（約 25 GB）を削除
> - 確認: CI と同じ import チェック（14 モジュール）、テスト 5 件、`DRY_RUN=1 bash paper/run_all.sh` のコマンド列（416 行、タイムスタンプ以外は削除前と同じ）
> - 以下の表で D・E にしていたこれらのファイルは、もう存在しない。残る D は simple・actual_cost の計算モジュール、BigSubs、`src/rewrite/enhanced_mv_generator.py` の 4 つ

## 1. 調べ方

1. **入口の洗い出し**: `paper/*.sh`（`common.sh` の `run_main` / `run_postopt` / `run_phase6` が渡すオプションを含む）、`paper_figures/make_all.sh`、CI（`.github/workflows/tests.yml`）、`docker/`、`dashboard/`、`tests/`、`scripts/redbench_synthesizer/`
2. **静的な import グラフ**: 全 Python ファイル 128 個を AST で解析した。ファイル先頭の import（必ず実行される）と、関数内の import（その関数が呼ばれたときだけ実行される）を分けて記録した。関数内の import は、呼び出し元の分岐条件を読み、論文のオプションで通るかを判定した
3. **実際に動かして確認**: 論文と同じオプションで、スクラッチの実験ディレクトリ（`--config`）で実行した。`python -X importtime` で、実際に読み込まれたモジュールを記録した
   - 実行したもの: Phase 2・3（`job-ceb-2` から 10 クエリを抜き出したセット）、Phase 5.5、Phase 6・7・8（static・dynamic）、Phase 6（adaptive）
   - DB に書き込む Phase 1・5・9 は動かさず、コードを読んで判定した
   - Phase 4 は、`migration/enumerate_simple_migration_plan.py` がリポジトリの `03_parsed/` と `04_migration/` を固定のパスで読み書きするため（`--config` が効かない）、スクラッチでは動かせない。コードを読んで判定した
   - 結果: 実際に読み込まれたファイルは、すべて静的解析で「到達する」と判定したものに含まれていた（食い違いなし）
4. **pickle の参照**: `03_parsed/*/qp_class.pkl` 7 本（約 43 GB）と `sparse_base.pkl` を走査し、クラスの参照（`STACK_GLOBAL`）を集めた
   - `job-ceb-2`・`Redbench_synthetic`: `config.settings`（`Settings` と各 `*Config`）、`src.core.models`（`NonLeafNodeInfo`、`JoinCondition`）、`src.core.query_manager`、`src.core.query_parser`
   - `job-ceb-2-q{20000..100000}`: `core.sparse_structures`（`SparseQP`、`SparseMatrix`、`SparseQM`、`SparseX`）
   - `sparse_base.pkl`: 組み込みの型だけ
   - → どれも「必要」のファイル。`*_distinct.py` にも同名のクラスがあるが、pickle が参照しているのは通常版
5. **文字列での参照**: README・シェルスクリプト・Python の中で、ファイル名やパスとして参照されているかを grep で確認した

## 2. 判定の区分

| 区分 | 意味 | 扱い |
|---|---|---|
| **A 必要** | 論文の実験（前処理〜ベンチマーク）で実行される | 残す |
| **B 必要（周辺）** | 図表・テスト・CI・Docker・ダッシュボード・入力データの作成で使う | 残す |
| **C import のためだけに必要** | 論文の実験では中身を使わないが、使うファイルが import しているので、今移すと動かなくなる | import を直せば移せる |
| **D 論文では使わないオプション** | 論文と違うオプションを指定したときだけ使う（コードとしては生きている） | 残すか移すかを決める |
| **E 不要** | どの入口からも届かず、どこからも参照されていない | archive へ移せる |

## 3. Python ファイルの判定

### scripts/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `run_experiment_normal.py` | A | 実験の本体 |
| `recalculate_costs.py` | A | Phase 5.5 |
| `extract_sparse_base.py`、`generate_synthetic_scaling.py` | A | RQ1 のクエリ数スケーリング（`rq1_exp1_3_query_scaling.sh`） |
| `__init__.py` | A | `from scripts.recalculate_costs import ...` に必要 |
| `redbench_synthesizer/*.py` | B | Redbench_synthetic の作成手順（README の付録から案内） |
| `run_utility_benchmark.py`、`run_utility_optimization.py` | E | 旧スクリプト。どこからも呼ばれていない（`run_ex*.sh` の旧版からも呼ばれていない） |
| `setup_imdb.py` | E | DB の構築は `Dockerfile` と `docker/` に置き換え済み |
| `scratch/reduce_sql_width.py` | E | 使い捨て。旧データのパスが直書き |

### core/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `time_dependent_optimizer.py`、`io_loaders.py`、`sparse_structures.py` | A | Phase 6（全モード）。`sparse_structures` は合成セットの pickle も参照している |
| `cf_pruner.py`、`local_ilp_optimizer.py`、`workload_summary_tree.py` | A | Phase 6 のプルーニング（`--use-pruning`）。テストでも使う |
| `utility_v2.py` | A | Phase 6 static（`--static-algorithm utility`） |
| `two_step_optimizer.py` | A | Phase 6 adaptive |
| `__init__.py` | A | |
| `small_test_schema_provider.py` | C | `core/__init__.py` が import しているだけで、どこでも使われていない |
| `utility_pruner.py`、`utility_pruner_iterative.py`、`utility_pruner_iterative_helpers.py`、`utility_pruner_simple.py` | E | 候補同士でしか import されていない |
| `utility_pruner copy.py`、`two_step_optimizer copy.py` | E | 手作業のコピー |

### src/core/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `query_parser.py`、`query_manager.py`、`models.py` | A | Phase 2 以降すべて。pickle も参照している |
| `parse_exporter.py` | A | Phase 3 |
| `__init__.py` | A | |
| `query_parser_distinct.py`、`query_manager_distinct.py` | E | どこからも import されず、pickle も参照していない |

### src/optimization/

`run_experiment_normal.py` は先頭で `from src.optimization.factory import OptimizerFactory` をしているが、`OptimizerFactory` は一度も使っていない。この import のせいで、`src/optimization/__init__.py` が最適化モジュール 7 つをすべて読み込む。

| ファイル | 区分 | 根拠 |
|---|---|---|
| `base.py` | A | static が使う `UtilityOptimizerV2`（`core/utility_v2.py`）の基底クラス |
| `normal.py` | C | static の処理では毎回 import されるが、使うのは `--static-algorithm normal`／`both` のときだけ |
| `bigsubs.py` | D | `--static-algorithm bigsubs`／`both` のときだけ。`__init__.py` と `factory.py` も import している |
| `factory.py` | C | 上記の使っていない import のためだけ |
| `frequency.py`、`utility.py`、`utility_capacity.py` | C | `__init__.py` と `factory.py` が import しているだけ |
| `__init__.py` | A | |

### src/rewrite/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `query_rewriter.py`、`mv_generator.py`、`sql_parser.py`、`join_graph.py` | A | Phase 8（実行で確認） |
| `schema_provider.py` | A | Phase 4（`GetSimpleMigrationPlans` と `SimpleMVSQLGenerator` が作る） |
| `schema.py` | A | `mv_generator.py` と `schema_provider.py` が使う |
| `__init__.py` | A | 配下のモジュールをまとめて import している |
| `enhanced_mv_generator.py` | D | `BaseILPOptimizer.get_materialized_views(generate_sql=True)` のときだけ。`True` で呼ぶ箇所はない |
| `advanced_rewriter.py`、`query_graph.py` | E | どこからも import されていない |

### src/ のその他

| ファイル | 区分 | 根拠 |
|---|---|---|
| `src/__init__.py`、`src/utils/__init__.py` | A | |
| `src/utils/legacy.py` | A | `run_experiment_normal.py`、`query_parser.py`、`query_rewriter.py` が使う |
| `src/utils/file_utils.py`、`logging_utils.py`、`validators.py` | E | どこからも import されていない |
| `src/database/`（4 ファイル） | E | どこからも import されていない |
| `src/benchmark/`（2 ファイル） | E | どこからも import されていない（ベンチマークは `benchmark/` を使う） |
| `src/estimation/neurocard_wrapper.py` | D | Phase 5 の `--use-neurocard` のときだけ |
| `src/estimation/sql_to_neurocard_csv.py` | E | どこからも import されていない（NeuroCard 用 CSV を作る単体スクリプト） |
| `src/estimation/queries_for_neurocard{.csv,_mapping.json}` | E | 上のスクリプトの出力。読むコードはない |

### migration/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `enumerate_simple_migration_plan.py` | A | Phase 4 |
| `sampling_migration_cost_calculator_high.py` | A | Phase 5（`--sampling-rate high`。今の `00_prepare.sh`） |
| `sampling_migration_cost_calculator.py` | A | Phase 5（低サンプル率）。論文の元のデータでは Redbench_synthetic の前処理に使った |
| `__init__.py` | A | |
| `simple_migration_cost_calculator.py` | D | Phase 5 で `--use-sampling` を付けないとき |
| `neurocard_migration_cost_calculator.py` | D | `--use-neurocard` |
| `deepdb_migration_cost_calculator.py`、`deepdb_estimator.py` | D | `--use-deepdb` |
| `actual_cost_migration_calculator.py` | D | クエリセットが `job_real` のとき（`job_real` は git の管理から外した） |

### mv_generation/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `original_sql_join_extractor.py` | A | Phase 2（`QueryParser._load_original_sql_conditions`） |
| `simple_mv_sql_generator.py`、`enhanced_mv_generator.py`、`comma_join_rewriter.py` | A | Phase 4 の MV 定義の生成（`EnhancedMVGenerator` と `CommaJoinRewriter` を実際に呼んでいる） |
| `__init__.py` | A | |

### benchmark/、utils/、config/

| ファイル | 区分 | 根拠 |
|---|---|---|
| `benchmark/time_dependent_query_executor.py`、`benchmark/__init__.py` | A | Phase 9 |
| `benchmark/time_dependent_query_executor copy.py` | E | 手作業のコピー |
| `utils/postgres_executor.py`、`utils/__init__.py` | A | Phase 1・5・9 の DB 接続（Docker 経由） |
| `utils/analyze_benchmark_results.py`、`utils/plot_benchmark.py`、`utils/inspect_pickle.py` | E | どこからも import・実行されていない |
| `utils/csv_exporter.py` | E | 構文エラーがあり、import もされていない |
| `config/settings.py`、`config/__init__.py` | A | 全体の設定。pickle も参照している |

### 周辺（区分 B）

| ファイル | 根拠 |
|---|---|
| `paper_figures/*.py`（9 ファイル）、`paper_figures/make_all.sh` | 論文の図表。CI でも再生成する |
| `tests/*.py`、`tests/data/` | CI |
| `dashboard/dashboard_api.py`、`dashboard.html`、`dashboard_static/` | ダッシュボード。`qp_class.pkl` を読むので `src/core/*` と `config/settings.py` が必要 |

## 4. Python 以外のファイル

| ファイル | 区分 | 根拠 |
|---|---|---|
| `paper/*.sh`、`paper/README.md` | A | 実験の実行スクリプト |
| `config/default.yaml` | A | `Settings()` が読む |
| `config/experiments/ceb_benchmark.yaml`、`job_benchmark.yaml` | E | どこからも読まれていない |
| `Dockerfile`、`.dockerignore`、`docker/*` | B | 実験環境（DB コンテナ） |
| `requirements.txt`、`pyproject.toml`、`uv.lock`、`pytest.ini`、`.github/` | B | 依存と CI |
| `scripts/shell/*.sh`（19 本） | E | `paper/` に置き換え済み。旧スクリプト同士でしか参照していない。`run_ex1_1-ceb.sh` は頻度ファイルのサフィックスが論文と違い、誤用の元になる |
| `scripts/DATABASE_SETUP.md` | E | 旧構成の手順書。`docker/README.md` に置き換え済み |
| `scripts/progress/scaling_pruning/summary.txt` | E | 旧実験のメモ |
| `core/objective_function.md` | 文書 | 定式化のメモ。実験には不要だが、コードの理解に役立つ |
| `progress/` の Python 21 ファイル（`ex1_1/`、`ex4/`、`scaling_pruning/` など） | 記録 | 旧版の図表スクリプト。`paper_figures/` に置き換え済みで、実験には不要。作業メモとしての扱いは TODO の 12（公開に含めるか）で決める |
| `small_docs/` | 記録 | 作業メモと他の論文の資料。実験には不要（TODO の 12） |
| `Redbench/` | B | 入力ワークロードの生成ツール（上流） |

## 5. まとめ

| 区分 | Python ファイル数 | 主なもの |
|---|---|---|
| A 必要 | 46 | 上の表 |
| B 必要（周辺） | 18 | 図表・テスト・ダッシュボード・Redbench synthesizer |
| C import のためだけ | 6 | `src/optimization/{factory,normal,frequency,utility,utility_capacity}.py`、`core/small_test_schema_provider.py` |
| D 論文では使わないオプション | 8 | NeuroCard・DeepDB・simple・actual_cost の計算モジュールと `deepdb_estimator.py`、`neurocard_wrapper.py`、BigSubs、`src/rewrite/enhanced_mv_generator.py` |
| E 不要 | 29 | `* copy.py` 3、`core/utility_pruner*.py` 4、`src/core/*_distinct.py` 2、`src/database/` 4、`src/benchmark/` 2、`src/rewrite/{advanced_rewriter,query_graph}.py` 2、`src/utils/{file_utils,logging_utils,validators}.py` 3、`src/estimation/sql_to_neurocard_csv.py` 1、`utils/` 4、`scripts/{run_utility_benchmark,run_utility_optimization,setup_imdb}.py` 3、`scripts/scratch/` 1 |

このほかの E: `scripts/shell/` 19 本、`scripts/DATABASE_SETUP.md`、`scripts/progress/`、`config/experiments/`、`src/estimation/` のデータ 2 ファイル。

（A〜E の合計は `progress/` の 21 ファイルを除いた 107 ファイル。）

## 6. 移すときの注意

- **E はそのまま移せる**: どの入口からも届かず、pickle も参照していない。移したあと、CI の import チェックと `DRY_RUN=1 bash paper/run_all.sh` のコマンド列が変わらないことを確かめる
- **C を移すにはコードの修正が要る**:
  - `run_experiment_normal.py` の使っていない `from src.optimization.factory import OptimizerFactory` を消す
  - `src/optimization/__init__.py` が 7 モジュールをまとめて import するのをやめる
  - `normal.py` は static の処理で毎回 import されるので、`--static-algorithm normal` を残すなら残す
  - `core/__init__.py` から `SmallTestSchemaProvider` を外す
- **D は機能として残すかどうかの判断**: 論文の再現には不要。README ではオプションとして案内していないので、移しても再現には影響しない。ただし `run_experiment_normal.py` の `--use-neurocard` などの引数も合わせて整理する必要がある
- **気づいた問題（今回は直していない）**: `migration/enumerate_simple_migration_plan.py` は、`--config` で指定した実験ディレクトリではなく、リポジトリの `03_parsed/` と `04_migration/` を固定のパスで読み書きする。通常の使い方（リポジトリの直下で実行）では問題ないが、実験ディレクトリを変えると Phase 4 だけ別の場所を見る

## 7. 確認できていないこと

- Phase 1・5・9 は動かしていない。import はコードを読んで判定した（関数内の import は Phase 5 の計算モジュールの選択と Phase 9 の `benchmark` だけ）
- Phase 4 と adaptive の Phase 7・8 は動かしていない。Phase 7・8 は dynamic と同じコードを通る
