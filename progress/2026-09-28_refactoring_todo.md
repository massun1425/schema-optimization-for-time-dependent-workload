# 論文提出に向けたリファクタリング: 残作業リスト

作成日: 2026-09-28

これまでに整えたもの:
- `paper/`: 実験を再現するシェルスクリプト。出力は `time_dependent_output/rq*/`
- `paper_figures/`: `rq*/` から論文の図表を作るスクリプト
- `docker/` と修正済みの `Dockerfile`: 実験環境のコンテナの作成と検証
- 英語の `README.md`、CI（`.github/workflows/tests.yml`）
- 不要ファイルの archive への移動と、不要データの削除（約 115GB）

根拠となる調査は `progress/2026-09-28_paper_experiment_inventory.md` を参照。

**方針: 実験スクリプトは時間がかかる（全体で約 3 週間）ため、今回は実行しない。**
実行が必要な作業は、最後の「実験を動かすときにやること」に分けた。

---

## 優先度: 高（提出・再現に直接関わる）

### 1. 既存の論文結果を `rq*/` 構成に配置する
- [x] 既存の結果（`*_ok` など）を **`paper_results/`**（git 管理下、`rq*/` と同じ構成）にコピーした
  - 実験を再実行したときに上書きされないよう、`time_dependent_output/rq*/` とは別のフォルダにした
  - 収集スクリプトは `paper_results/collect_paper_results.sh`。コピーのみで、既存ファイルは上書きしない
  - 論文の図表も `paper_results/figures/` に生成した（12 枚の図と表 2 本が論文のものと一致し、再生成してもバイト単位で同一）
- [x] `bash paper_figures/make_all.sh --td-dir paper_results` で論文の図表が生成できることを確認した

（2026-09-28 完了）
- 作成したのは 161 ファイル（JSON 158 本と DNF の印 3 つ）。ほかに `README.md` と `SHA256SUMS` を置いた
- 元データ（`time_dependent_output/`）に変化がないことを確認した
- 12 枚の図と表 2 本が、論文の図表とピクセル単位で一致した
- 作業ツリー上は 1.6GB、圧縮後は 0.11GB。最大ファイルは 49.8MiB

- **理由**: `paper/` はまだ一度も実行していないので `rq*/` が存在せず、`paper_figures/` で図を作れない状態になっている。
- **対応付け**: 模擬検証で使ったものと同じで、この対応付けで 12 枚の図と表 2 本が論文の図表と一致することを確認済み。

  | `rq*/` | 元データ |
  |---|---|
  | `rq1/exp1_1/job-ceb-2/` | `job-ceb-2/result_500M_ok/` |
  | `rq1/exp1_1/Redbench_synthetic/`、`rq2/` | `ex2_500M_ok/` |
  | `rq1/exp1_2/` | `job-ceb-2/result_scaling_time_ok/` |
  | `rq1/exp1_3/job-ceb-2-q{N}/` | `job-ceb-2-q{N}/`（プルーニングなしは `_wo` に改名。60k/80k/100k は DNF の印を置く） |
  | `rq3/` | `ex3_500M_ok/` |
  | `rq4/{24_2_10,24_mono,24_peak}/b*/` | `ex4_ok_{cycle,mono,peak}/b*/` |

- **注意**: 移動ではなくコピーで行い、元の `*_ok` は残す。
- **完了条件**: `make_all.sh` が成功し、出力が論文の図表と一致する。

### 0. 論文に Artifacts 節を追加する（EDBT の必須要件）
- [ ] 参考文献の直前に「Artifacts」という節を置き、すべての成果物の入手方法と使い方を書く（ページ数に数えない）
  - GitHub のリポジトリへのリンク（アクセスを監視しないページであること）
  - 論文の結果と図表が `paper_results/` にあり、実験を動かさずに図表を再生成できること
  - 実験の再現手順（README の手順、Docker による環境、実行時間の目安）
- [ ] 投稿前に、GitHub へ push した状態でリンク先から README どおりに図表を再生成できるか確かめる
- 締め切り: EDBT 2027 第 3 サイクルの投稿は 2026-10-07

### 2. 依存の定義を実態に合わせる
- [x] `requirements.txt`: 実験で使った版に固定。matplotlib を追加し、使わない torch を削除。ダッシュボード用の fastapi・uvicorn は同じファイルにまとめた
- [x] `pyproject.toml`: 依存を `requirements.txt` と同じ版に固定（numpy・matplotlib・fastapi・uvicorn を追加、`gurobipy==12.0.1`、`python-dotenv` を削除）、`requires-python = ">=3.12"`、Black・Ruff・mypy の対象を 3.12 に変更
- [x] `uv.lock` を作り直し（`uv lock --check` で整合を確認）
- [x] README の回避手順を削除し、CI も `pip install -r requirements.txt` を使うように変更

（2026-09-28 完了。新しい仮想環境で `pip install -r requirements.txt` だけを実行して、import チェック・テスト・Fig. 5/6 の生成が通り、図が論文のものとピクセル単位で一致することを確認。`uv sync --frozen` でも同じ版の環境が作れることを確認）

- **理由**: 今の定義どおりにインストールすると図が作れないうえ、不要な重い依存（torch）が入る。
- **完了条件**: 新しい仮想環境で `pip install -r requirements.txt` だけを実行し、import チェックと図表生成が通る。

### 3. 論文本文の修正（論文側の作業）
- [ ] Abstract / Intro の「最大 24.6%（Static 比）」「最大 45.6%（Adapt 比）」: 一致する結果がない。現在のデータに基づく値に直す
- [ ] 5.2.1 節の「Static 比 62.8%」→ **63.3%** に直す（Adapt 比 87.4% はそのまま）
  - 2026-09-28 再確認: `ex2_500M_ok` から計算すると、初期 MV 構築を除くと 62.77%、含めると 63.31%
  - Static の `total_benchmark_time`（141,991.6 s）＝ 各時刻の合計（139,951.7 s）＋ 初期 MV 構築（2,039.9 s）
  - 論文 5.1.4 節の定義（Static は初期 MV 構築を最初の時刻に含める）と、Fig. 7 の Static 系列の合計、Fig. 10 の recall 100% の値（どちらも 141,991.6 s）は、構築時間を含めている
  - 62.8% は `progress/gen_data_summary.py` が構築時間を含めずに合計した値だった
- [ ] 5.1.2 節の「2,294 クエリ」→ **2,284** に直す
  - 2026-09-28 再確認: 次の 6 つがすべて 2,284
    - SQL ファイル数
    - EXPLAIN JSON 数
    - `parse_summary.json` の `num_queries`
    - 頻度ファイル（`_2h_x2_50x`）のキー数
    - 1 回以上実行されるクエリ数
    - ベンチマークで実際に実行されたクエリ数
  - git の履歴でも最初（2026-06-04）から 2,284 で、2,294 の出どころは見つからない（誤記と思われる）
  - 中身が同じ SQL が 2 組あるため、内容で数えると 2,282。論文の「クエリ数」としてはファイル数・頻度ファイルと一致する 2,284 が妥当
- [ ] 5.1.1 節の「PostgreSQL 18.3」→ 実際は 18.4
- [ ] （任意）Fig. 8 のキャプションの「2500 queries」→ 正確には **2,515**（JOB 113 + CEB 2,402）
  - 2026-09-28 確認: SQL ファイル数、EXPLAIN JSON 数、`parse_summary.json`、使った頻度ファイル 8 種のキー数、ベンチマークで実行されたクエリ数（3 パターン）がすべて 2,515
  - Redbench を 2,284 と正確に書くなら、こちらもそろえるとよい
  - Fig. 9 の合成セットは 20,000〜100,000 クエリちょうどで、論文の表記どおり

根拠となる数値は棚卸し md の §6 と `progress/2026-08-09_experiment_data_summary.md` にある。

- [ ] 4.3 節のサンプリングの記述を確認する
  - 2026-09-28 に `paper/00_prepare.sh` を変更し、Redbench_synthetic も高サンプル率版（`TABLESAMPLE BERNOULLI`、大きいテーブルの 10〜30%）を使うようにした
  - ただし、論文の Redbench の結果（Fig. 7 の Redbench パネル、Fig. 10、`paper_results/`）は、元の低サンプル率版（ハッシュによる相関サンプリング、1〜10%）のコストで出ている
  - EXPLAIN の結果も実行のたびに変わりうるため、再実行で結果が多少変わるのは前提どおりとして、Redbench のやり直しは行わない（2026-09-28 判断）

### 4. 結果データの公開方法を決める

（2026-09-28 途中経過）
- 最終結果と図表は `paper_results/` に入れて GitHub に含めることにした（1 の項目）
- 中間結果は GitHub に含めず、前処理（`paper/00_prepare.sh`）を読者に再実行してもらう方針にした
  - 理由: `04_migration` のノード ID は Phase 2 が EXPLAIN の結果から振るため、単体で配布しても、読者が Phase 1 をやり直すと対応が保証できない
  - job-ceb-2 と Redbench_synthetic の `04_migration` のコピーは `04_migration_paper/` に残してあるが、`.gitignore` の対象にした（手元の来歴用）
- [x] 公開方法を決めた: 最終結果と図表は `paper_results/` として GitHub に含める。中間結果（`03_parsed/` など）は含めず、読者に前処理を再実行してもらう
- [x] README に `paper_results/` の説明と、図表を再生成する方法を書いた（別途のダウンロードは不要になった）

- **理由**: どちらのデータも git 管理外で、今のままでは第三者が論文の結果そのものを確認できない。

---

## 優先度: 中（リファクタリングの残り）

### 5. 未使用のコードと古いスクリプトを archive へ移す
- [ ] 未使用のコード（棚卸し md の §4.1）
  - `benchmark/time_dependent_query_executor copy.py`、`core/two_step_optimizer copy.py`、`core/utility_pruner copy.py`
  - `core/utility_pruner{,_iterative,_iterative_helpers,_simple}.py`、`src/core/{query_manager,query_parser}_distinct.py`
  - `src/rewrite/{advanced_rewriter,query_graph}.py`、`src/database/`、`src/benchmark/`、`src/estimation/`
  - `src/utils/{file_utils,logging_utils,validators}.py`
  - `migration/` の NeuroCard・DeepDB・actual_cost・simple の各計算モジュールと `deepdb_estimator.py`
  - `utils/{analyze_benchmark_results,csv_exporter,plot_benchmark}.py`
  - `scripts/run_utility_{benchmark,optimization}.py`、`scripts/setup_imdb.py`、`scripts/scratch/`、`scripts/progress/`
- [ ] `scripts/shell/` の旧スクリプト 19 本（`paper/` に置き換え済み）。特に `run_ex1_1-ceb.sh` は頻度ファイルのサフィックスが論文と違い、誤用の元になる
- [ ] 古い手順書 `scripts/DATABASE_SETUP.md`（移動済みのファイルや旧構成を参照している）
- [ ] 使っていない設定 `config/experiments/*.yaml`

- **注意**: `src/optimization/{bigsubs,frequency,utility,utility_capacity}.py` は、使っていないが `factory.py` が import しているので、そのまま移すと壊れる。移すなら `factory.py` も直す。
- **完了条件**: import チェック（CI と同じもの）と `DRY_RUN=1 bash paper/run_all.sh` のコマンド列が、移動前と変わらない。

（2026-09-28 途中までの検証結果。pickle の走査は時間がかかるため中断し、後回し）
- 実験で使う入口（`paper/` が呼ぶ 4 スクリプト、図表スクリプト、CI のテスト、ダッシュボード）から import を辿ると、Python ファイル 104 個のうち 33 個には、条件分岐の中の import を含めても到達しない
  - 到達しないもの: 上の一覧の `* copy.py` 3 個、`core/utility_pruner*.py` 4 個、`src/core/*_distinct.py`、`src/rewrite/{advanced_rewriter,query_graph}.py`、`src/database/`、`src/benchmark/`、`src/estimation/sql_to_neurocard_csv.py`、`src/utils/{file_utils,logging_utils,validators}.py`、`utils/{analyze_benchmark_results,csv_exporter,plot_benchmark,inspect_pickle}.py`、`scripts/{run_utility_benchmark,run_utility_optimization,setup_imdb}.py`、`scripts/scratch/`
  - Redbench のワークロード生成ツール（`scripts/generate_queryset_from_workload_csv.py`、`normalize_queryset_table_versions.py`、`merge_query_folders*.py`）も到達しないが、README の付録で案内しているので残す
- 到達はするが、論文の実験の条件では通らない分岐でしか import されないもの
  - `migration/{actual_cost,neurocard,deepdb,simple}_*` と `deepdb_estimator.py`、`src/estimation/neurocard_wrapper.py`: Phase 5 で `--use-sampling` 以外を選んだとき、または `job_real` のときだけ
  - `src/rewrite/enhanced_mv_generator.py`: `generate_sql=True` のときだけ（呼び出し元はない）
- 注意: `run_experiment_normal.py` は `OptimizerFactory` を import しているが使っていない。この import によって `src/optimization/__init__.py` が最適化モジュール 7 つ（`bigsubs`・`frequency`・`utility`・`utility_capacity`・`normal` など）を毎回 import する。これらを移す前に、この import と `__init__.py` を整理する必要がある（`base.py` は Static が使う `UtilityOptimizerV2` の基底クラスなので必要）
- 文字列による動的な import（`importlib` など）はない。候補名への文字列参照は、候補ファイル同士の間にしかない
- 未確認: pickle（`qp_class.pkl`）が参照しているモジュール名。候補を移す前に確認する

### 6. 実行経路のコードを英語化する
- [ ] 実行経路のコード 44 ファイルにある日本語のコメント・docstring・ログメッセージを英語にする（`scripts/run_experiment_normal.py`、`core/`、`src/`、`migration/` など）

- **理由**: リポジトリは英語で書くという方針に合わせるため（国際会議の成果物）。
- **注意**: ロジックは変えない。ログの文言を変えると、過去のログとの比較や grep がしにくくなる点に注意。
- **完了条件**: 5 と同じ回帰チェックが通る。

### 7. 小さな不具合を直す
- [x] `--phase 0` が存在しないメソッド `phase0_setup` を呼んでいる → 選択肢から外した（DB のセットアップは `docker/create_container.sh` が担う）
- [x] `run_experiment_normal.py` の設定に関するコメントを、実際の動作（`config/default.yaml` か `$CONFIG_PATH` を読み、`DB_*` の環境変数で上書き）に合わせて英語で書き直した
- [x] `migration/enumerate_simple_migration_plan.py` の `__main__` を、`run_experiment_normal.py` と同じ `Settings()` を使うように直した
- [x] `tests/test_pruning.py` のプロジェクトルートの計算を直した（別のディレクトリから素の `pytest` で実行しても import に成功することを確認）
- [ ] `utils/csv_exporter.py` の構文エラー（5 で archive に移すなら不要）

### 8. 実行条件を結果 JSON に保存する
- [ ] `run_experiment_normal.py` が、実行時の引数（`--freq-weight`、`--sampling-rate`、`--pruning-parallel`、`--pruning-workers` など）と、コードのバージョン（git のコミット）を結果 JSON に書き出すようにする

- **理由**: 今は一部の条件が結果から判別できず、元のシェルスクリプトの記述を信じるしかなかった。
- **注意**: 結果の JSON 形式が変わるので、`paper_figures/` が読むフィールドを壊さないようにする（追加だけにする）。

### 9. テストと CI を強化する
- [x] CI で、`paper_results/` から論文の図表（Fig. 5〜11、Table 2）をすべて再生成し、`paper_results/figures/` とバイト単位で一致するかを確かめるようにした
- [x] 空のテスト 2 件を、最適解を手計算で求められる小さな問題で検証する中身にした（`tests/test_pruning.py`。LocalILP の固定制約、TimeDependentOptimizer との一致、プルーニングで劣った候補が除かれ最適解が変わらないこと、並列と逐次で有望集合が同じこと）
- [x] 回帰テストを追加した（`tests/test_optimizer_regression.py` と期待値 `tests/data/optimizer_regression_expected.json`。seed 固定の 12 クエリ・15 候補・6 時刻の問題。期待値は `--update` で作り直せる）
- [x] Gurobi のライセンスが使えないときは最適化のテストを skip するようにした（`tests/conftest.py` と `@pytest.mark.gurobi`）。pip 版 gurobipy 12.0.1 付属の無償ライセンスが 2026-11-23 に切れるため
- [x] lint の扱いを決めた: CI から `lint` ジョブを外した（2026-09-29）。2025-10 の初期設定で入ったが、最初から失敗しても CI を止めない設定で、一度も機能していなかった
  - Black と Ruff の設定は `pyproject.toml` に残してあるので、手元では `black` / `ruff check` を使える
  - 参考（2026-09-28 時点）: 今回作ったコード（`paper_figures/`・`tests/`）は 11 ファイルが整形対象・指摘 7 件、既存の `src/` は 1,228 件、`core/`・`scripts/` などは 2,989 件

---

## 優先度: 低（来歴・公開前の整理）

### 10. 入力データの作り方を記録する
- [ ] `job-ceb-2`（JOB + CEB の 2,515 クエリ）の作り方と、頻度ファイル（`_24_2_10` / `_24_mono` / `_24_peak`、`_{12..42}_mono`）の生成方法をスクリプトか文書に残す
- [ ] Redbench synthetic の作り方（cluster 53 と 55 の結合、10x → 50x のスケーリング）を記録する。`archive/` の `fix_combined.py`、`make_3_combined.py`、`merge_freq_files.py` が手がかり

### 11. 論文で使っていないデータを整理する
- [ ] `01_queries/` の論文で使っていないセット（`job`、`job_real`、`explicit_join`、`job-ceb-2-q10000`、`job-ceb-2-x2`）
- [ ] 対応する `02_json/`、`04_migration/`、`time_dependent_output/` の旧データ（`cluster_*` など）
- [ ] `01_queries/job_like/` が作業ツリー上で削除され、未コミットになっている → 意図したものか確認してコミットする

### 12. 公開に含めるものを決める
- [ ] `progress/`（日本語の作業メモ。このファイルも含む）
- [ ] `small_docs/`（他の論文の PDF や発表資料を含む）
- [ ] `dashboard/`
- [ ] `Redbench/`（第三者のツール。ライセンスと出典の表記を確認する）

### 14. IMDB データのチェックサムを記録する（任意）
- [ ] Dockerfile が外部 URL から取得する IMDB データの SHA-256 を記録し、ビルド時に照合する
  - 優先度を下げた理由（2026-09-28）: データの同一性は `docker/verify_env.sh` の行数チェック（21 テーブル）とインデックスのチェックで確認できる。JOB の標準データで、EDBT の要件でもない
  - 実施するなら、アーカイブの再ダウンロード（約 1.2GB）が必要。イメージの中の CSV 21 個のチェックサムを記録する方法もある

### 13. 文書を最新の状態に更新する
- [ ] 棚卸し md（`progress/2026-09-28_paper_experiment_inventory.md`）の「git 管理外」という記述を、入力データのコミット後の状態に合わせて直す

---

## 実験を動かすときにやること（今回は実施しない）

- [ ] **短い実走で動作確認する**: DB 不要で短く終わる RQ1 Exp1-2 の T=12 だけを実行し（`TIMESTEPS=12 bash paper/rq1_exp1_2_timestep_scaling.sh`。プルーニングありとなしで計 15 分程度）、次を確かめる
  - 結果が `rq1/exp1_2/` に回収されること
  - staging の既存ファイルが元の場所に戻ること
  - 有望 MV 集合と目的関数値が論文の結果（`result_scaling_time_ok`）と一致すること
- [ ] リファクタリング（5〜8）のあとにも、同じ実走で結果が変わっていないことを確認する
- [ ] 全実験を再実行する場合は `nohup bash paper/run_all.sh > paper_run_all.log 2>&1 &`（約 3 週間）。実行時間の目安は README の 4.2 節を参照
