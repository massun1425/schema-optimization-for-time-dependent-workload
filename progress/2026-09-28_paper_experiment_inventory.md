# 論文（EDBT2026「Schema Optimization for Time-Dependent Workloads」）実験ファイル棚卸し

作成日: 2026-09-28 ／ 目的: 論文提出用リファクタリングに向け、論文の図表を作っている結果データ、それを再現するのに必要なファイル、補助ファイルを洗い出す。
**本調査ではリポジトリのファイルを一切変更していない**（このファイルを新規作成したのみ。`__pycache__` も書かない設定で調べた）。

調べ方:
- 各プロットスクリプトの入力パスを読み、結果 JSON の中身（アルゴリズム名・`storage_budget`・候補数・時間）と論文の数値を突き合わせた。
- ベンチマーク結果に記録されている各時刻・各クエリの頻度を `01_queries/*/frequency_time_dependent*.json` と完全一致で照合し、実際に使われた頻度ファイルを特定した。
- 同一内容のコピーは md5 で判定した。
- コードの依存関係は、エントリポイントから AST で import を辿ったうえで、実行時 import（`-B`）でも確かめた。

---

## 0. 要点

- 論文の図表は **8 図 + 1 表 + 本文の数値**。対応する結果 JSON は計 **152 ファイル**。コピーの重複を除くと **128 ファイル**。
- 前処理の入力（`01_queries/job-ceb-2/`、`02_json`、`03_parsed`、`04_migration`）と `time_dependent_output/` は **すべて git 管理外**。Fig.10 と Fig.5 の生成スクリプトも git 管理外にある。
- 実際に論文の結果を出したコードは **53 ファイル**（§3.4）。
- 対応するシェルスクリプトのうち、**`run_ex1_1-ceb.sh` は現状では論文の結果を再現しない**（`_rand` / `_10x` を指している）。そのほかにも、出力先を手作業でリネームしている箇所や、スクリプト自体が存在しない実行がある（§5）。
- `Dockerfile` の COPY 元 `./data/` は `archive/data/` に移動しているため、**現状のままでは `docker build` が失敗する**。
- 論文本文の数値のうち、**Abstract / Intro の「24.6%」「45.6%」は現在のどの結果とも一致しない**（§6）。

---

## 1. 論文の図表と結果データの対応

| 論文 | 内容 | 図表ファイル（論文に入れるもの） | 生成スクリプト | 入力データ |
|---|---|---|---|---|
| Fig.5 | 頻度パターン（Cycles / Evolution / Growth） | `01_queries/job-ceb-2/frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf` | `01_queries/job-ceb-2/plot_frequency_patterns.py` ⚠git管理外 | `01_queries/job-ceb-2/frequency_time_dependent_{24_2_10,24_mono,24_peak}.json` |
| Fig.6 | Redbench の総実行回数 | `01_queries/Redbench_synthetic/plots/frequency_pattern_Redbench.pdf` | `01_queries/Redbench_synthetic/plot_frequency_total.py` | `01_queries/Redbench_synthetic/frequency_time_dependent_2h_x2_50x.json` |
| Fig.7 | 各時刻の実行時間（4 パネル） | `progress/ex1_1/timestep_time_{24_2_10,24_mono,24_peak}_static_init.pdf`、`progress/ex1_1/timestep_time_ex2_500M_static_init.pdf` | `progress/ex1_1/plot_timestep_time_static_init.py`、`progress/ex1_1/plot_timestep_time_ex2_static_init.py` | `time_dependent_output/job-ceb-2/result_500M_ok/`、`time_dependent_output/ex2_500M_ok/` |
| Fig.8 | 最適化時間 vs タイムステップ数 | `progress/scaling_timestep/timestep_bar.pdf` | `progress/scaling_timestep/plot_timestep.py` | `time_dependent_output/job-ceb-2/result_scaling_time_ok/` |
| Fig.9 | 最適化時間 vs クエリ数 | `progress/scaling_pruning/opt_time_query_scaling.pdf` | `progress/scaling_pruning/plot_opt_time_query_scaling.py` | `time_dependent_output/job-ceb-2-q{20000..100000}/` |
| Table 2 | プルーニング有無の比較 | `progress/ex3_500M/table3.tex` | `progress/ex3_500M/generate_table3.py` | `time_dependent_output/ex3_500M_ok/` |
| Fig.10 | 予測 recall に対する頑健性 | `time_dependent_output/ex2_500M_ok/ex2_500M_noise.pdf` | `time_dependent_output/ex2_500M_ok/plot_noise.py` ⚠git管理外 | `time_dependent_output/ex2_500M_ok/` |
| Fig.11 | 容量制約と総実行時間（3 パネル） | `progress/ex4/capacity_bar_all.pdf` | `progress/ex4/plot_capacity_all.py` | `time_dependent_output/ex4_ok_{cycle,mono,peak}/b{500,1000,1500,2000}/` |
| 本文の数値 | 2.03×、1.78×、87.4%、20.8 h など | `progress/2026-08-09_experiment_data_summary.md` | `progress/gen_data_summary.py` | 上記と同じ |

補足:
- **Fig.7 は `_static_init` 版を使っている。** Static の初期 MV 構築時間を t=1 に加算した版で、Cycles の Static t=1 は 19,494 s（加算前は 18,070 s）。論文の図とも一致する。`_static_init` の付かない `timestep_time_*.pdf` は論文では使っていない。
- **Fig.11 は `capacity_bar_all.pdf`（3 パネル版）を使っている。** `capacity_bar{,_mono,_peak}.pdf` は 1 パネルずつの旧版。
- すべてのプロットスクリプトは**プロジェクトルートから実行する前提**（相対パス）。例外は `plot_noise.py` で、自分自身のディレクトリを基準にする（`DIR = Path(__file__).parent`）。

---

## 2. 必要な結果ファイル（`time_dependent_output/` 内）

凡例: ★ 図表が直接読むファイル ／ ○ その最適化結果（来歴。図には使わないが、Phase 7〜9 の入力であり実行条件の根拠になる）

### 2.1 Fig.7（JOB+CEB の 3 パターン）: `time_dependent_output/job-ceb-2/result_500M_ok/`（18 ファイル）

`{fq}` = `24_2_10`（Cycles）/ `24_mono`（Evolution）/ `24_peak`（Growth）

| 手法 | ★ ベンチマーク結果 | ○ 最適化結果 |
|---|---|---|
| Proposed | `benchmark_results_dynamic_{fq}.json` | `td_mv_optimization_result_{fq}.json` |
| Adapt | `benchmark_results_adaptive_w4_{fq}.json` | `adaptive_mv_optimization_result_w4_{fq}.json` |
| Static | `benchmark_results_static_{fq}.json` | `static_mv_optimization_result_{fq}.json` |

- 使うフィールド: `timestep_results[t].total_time`。Static は `initial_mv_creation_time` を t=1 に加算する。
- 実行条件（JSON で確認）: B_max = 500 MB（`storage_budget` = 524,288,000）、T = 24、候補 26,312 → プルーニング後 1,656 / 1,772 / 1,648、Static の `algorithm` = `static_utility` / `timestep` = `average`。
- **`time_dependent_output/ex1_1_500M_ok/` の 18 ファイルは上記とバイト一致のコピー**（md5 で確認）。プロットスクリプトは `result_500M_ok` 側を読んでいる。
- 同じディレクトリにあるが論文では使っていないもの: `*_wo.json`（adaptive 6 本）、`*peloton*`（4 本）、`*static_bigsubs*`（6 本）、`*.pdf`（6 本）。

### 2.2 Fig.7（Redbench パネル）と Fig.10: `time_dependent_output/ex2_500M_ok/`（26 ファイル + スクリプト）

| 区分 | ファイル |
|---|---|
| ★ Proposed | `benchmark_results_dynamic_2h_x2_50x.json`（ノイズなし = recall 100%）、`benchmark_results_dynamic_2h_x2_50x_noise{5,10,…,50}.json`（10 本） |
| ★ Static | `benchmark_results_static_2h_x2_50x.json`、`benchmark_results_static_2h_x2_50x_noise{5,…,50}.json`（10 本） |
| ★ Adapt | `benchmark_results_adaptive_w4_2h_x2_50x.json`（ノイズの影響を受けないため 1 本のみ） |
| ○ 最適化結果 | `td_mv_optimization_result_2h_x2_50x.json`（候補 23,696 → 2,557）、`static_mv_optimization_result_2h_x2_50x.json`、`adaptive_mv_optimization_result_w4_2h_x2_50x.json` |
| 図の生成 | `plot_noise.py` → `ex2_500M_noise.pdf` / `.png` |

- recall = 100 − noise(%)。Fig.10 は `summary.total_benchmark_time` を使う。
- ノイズ付きの結果は Phase 9 のみを `--noise-ratio X --ease` で再実行したもの。最適化結果はノイズなしのものを共有している。

### 2.3 Table 2: `time_dependent_output/ex3_500M_ok/`（12 ファイル）

| 区分 | ファイル |
|---|---|
| With pruning | `td_mv_optimization_result_{fq}.json`、`benchmark_results_dynamic_{fq}.json` ← **`result_500M_ok` とバイト一致のコピー** |
| Without pruning | `td_mv_optimization_result_{fq}_wo.json`、`benchmark_results_dynamic_{fq}_wo.json`（この 6 本だけが固有のデータ） |

- 列の定義: 最適化時間 = `pruning_time_sec + solve_time_sec`、総実行時間 = `summary.total_benchmark_time`、目的関数値 = −`objective`/1000。

### 2.4 Fig.8: `time_dependent_output/job-ceb-2/result_scaling_time_ok/`（12 ファイル）

- `td_mv_optimization_result_{12,18,24,30,36,42}_mono_{wp,wo}.json`。縦軸は `phase_time_sec`。
- `*_48_mono_{wp,wo}.json` もあるが、論文の図は 42 までで 48 は使っていない。
- 実行ログ: `time_dependent_output/ex1_3/log/log_dynamic_*_mono_{wp,wo}.txt`。

### 2.5 Fig.9: `time_dependent_output/job-ceb-2-q{N}/`（12 ファイル）

| N | ★ Static | ★ Proposed (w/ pruning) | ★ Proposed (w/o pruning) |
|---|---|---|---|
| 20000, 40000 | `static_mv_optimization_result_24_mono.json` | `td_mv_optimization_result_24_mono_wp.json` | `td_mv_optimization_result_24_mono.json` |
| 60000, 80000, 100000 | 同上 | 同上 | なし（DNF） |

- Static は `execution_time`、Proposed は `phase_time_sec` を使う。
- DNF の根拠: `progress/scaling_pruning/nopruning_q60000.log` は Gurobi が 82,276 s 時点でも求解中のまま終わっている（24 h タイムアウト）。80k / 100k は打ち切りで未実行。
- 論文では使っていないもの: `*_seq.json`（逐次プルーニング版。目的関数値と有望 MV 集合は `_wp` と同じ）、`static_bigsubs_*`、`job-ceb-2-q10000/`、`job-ceb-2-x2/`。

### 2.6 Fig.11: `time_dependent_output/ex4_ok_{cycle,mono,peak}/b{500,1000,1500,2000}/`（72 ファイル）

各ディレクトリに次の 6 本がある（`{fq}` = cycle→`24_2_10`、mono→`24_mono`、peak→`24_peak`）:
- ★ `benchmark_results_{dynamic,static,adaptive_w4}_{fq}.json`（`summary.total_benchmark_time`。Static は初期構築を含む）
- ○ `td_mv_optimization_result_{fq}.json`、`static_mv_optimization_result_{fq}.json`、`adaptive_mv_optimization_result_w4_{fq}.json`

補足:
- **`b500/` の 18 本は `result_500M_ok` とバイト一致のコピー。**
- `ex4_ok_peak/b2500/` と `b3000/` は論文では使っていない。

### 2.7 集計

| ディレクトリ | 必要な本数 | 固有データ |
|---|---:|---:|
| job-ceb-2/result_500M_ok | 18 | 18 |
| ex2_500M_ok | 26 | 26 |
| ex3_500M_ok | 12 | 6 |
| job-ceb-2/result_scaling_time_ok | 12 | 12 |
| job-ceb-2-q{20k..100k} | 12 | 12 |
| ex4_ok_{cycle,mono,peak}/b500..b2000 | 72 | 54 |
| **計** | **152** | **128** |

### 2.8 `time_dependent_output/` にあるが論文では使っていないもの（参考）

`cluster_*`（6 個）、`job/`、`job_old/`、`job_plus/`、`job_real/`、`ex1_1/`（旧 job・100 MB 設定）、`ex1_2/`、`ex2/`、`ex3/`（ログの空ディレクトリ）、`ex4_old/`、`ex4_redbench/`、`Redbench_synthetic/result_*`（11 個）、`job-ceb-2/td_mv_optimization_result_{24,48}_mono.json`（直下の古い出力）。

> ⚠ `time_dependent_output/<set>/` 直下の `timestep_*.sql`、`static_initial_mvs.sql`、`jobs/`（Phase 7/8 の中間生成物）は**実行のたびに上書きされる**。現在残っているものは最後の実行（例: `job-ceb-2` は Aug 15 = ex4 peak の b3000）に対応しており、**論文の結果とは対応していない**。再現するときは、対応する最適化結果から Phase 7/8 を再生成する必要がある。

---

## 3. 実験結果を得るのに必要なファイル

### 3.1 実験パイプライン（全体像）

```
[前処理] Phase1 EXPLAIN → Phase2 parse → Phase3 annotate → Phase4 plans → Phase5 costs(sampling) → recalc
         (scripts/shell/run_ex0_job-ceb.sh / run_ex0_redbench.sh)
[本処理] Phase6 最適化 (dynamic / static / adaptive) → Phase7 MV SQL → Phase8 rewrite → Phase9 benchmark(--ease)
         (--phase post-opt で 6〜9 をまとめて実行。スケーラビリティ実験は --phase 6 のみで DB 不要)
```

### 3.2 環境

| ファイル | 用途 | 状態 |
|---|---|---|
| `Dockerfile` | PostgreSQL + IMDB（shared_buffers=2GB、work_mem=128MB、max_locks_per_transaction=256） | ⚠ `COPY ./data/schema.sql` と `./data/setup.sql` がリンク切れ（実体は `archive/data/`） |
| `archive/data/schema.sql`、`archive/data/setup.sql` | Dockerfile が COPY する DB スキーマとロード SQL | archive 配下に移動済み |
| `requirements.txt`、`pyproject.toml`、`uv.lock` | Python 3.12 の依存（gurobipy、psycopg2、sqlparse、numpy、matplotlib など） | |
| `gurobi.lic` / `.env`（`GRB_LICENSE_FILE`、`DB*`） | Gurobi ライセンスと DB 接続情報 | ⚠ 公開リポジトリに含めない |
| `config/default.yaml` | `Settings()` が自動で読む（`CONFIG_PATH` 未指定時）。DB 接続や timeout の設定 | コード中の「config.yaml を使わず」というコメントは誤解を招く。実際にはこのファイルが使われている |
| `config/__init__.py`、`config/settings.py` | 設定の読み込み | |

### 3.3 入力データ（すべて git 管理外。Redbench の SQL のみ git 管理下）

| クエリセット | 01_queries | 02_json | 03_parsed | 04_migration |
|---|---|---|---|---|
| `job-ceb-2`（2,515 クエリ、候補 26,312） | `*.sql` 2,515 本 + `frequency_time_dependent_{24_2_10,24_mono,24_peak}.json`（Fig.5/7/11/Table2）+ `_{12,18,24,30,36,42}_mono.json`（Fig.8） | `*.json` 2,515 本（51 MB） | `qp_class.pkl`（2.9 GB）、`parse_summary.json`、`sparse_base.pkl`（136 MB。合成セット生成用） | `simple_migration_plans.json`、`simple_migration_costs.json`（recalc 済み、`calc_method=pickle_recursive_v2`） |
| `Redbench_synthetic`（2,284 クエリ、候補 23,696） | `*.sql` 2,284 本 + `frequency_time_dependent_2h_x2_50x.json` | `*.json` 2,284 本 | `qp_class.pkl`（2.2 GB）、`parse_summary.json` | 同上 |
| `job-ceb-2-q{20000,40000,60000,80000,100000}`（合成） | `frequency_time_dependent_24_mono.json` | なし | `qp_class.pkl`（SparseQP 形式、2.1〜13 GB） | `simple_migration_costs.json` |

使われた頻度ファイルは、ベンチマーク結果の頻度との完全一致で確定させた:
- job-ceb-2 のすべての実験は **`_rand` なし**の版（`_24_2_10` / `_24_mono` / `_24_peak`）を使っている。24 時刻すべてで一致し、`_rand` 版とは 0〜16 時刻しか一致しない。
- Redbench は **`_2h_x2_50x`** を使っている。`_2h_x2` と `_2h_x2_10x` とは 0 時刻しか一致しない。
- 論文では使っていない頻度ファイル: `*_rand.json`（3 本）、`_48_mono.json`、Redbench の `_2h_x2.json` と `_2h_x2_10x.json`。

### 3.4 Python コード（実行時 import で確認した 53 ファイル）

**エントリポイント**
| ファイル | 役割 |
|---|---|
| `scripts/run_experiment_normal.py` | 全 Phase の本体（`--phase 1..9 / post-opt`） |
| `scripts/recalculate_costs.py` | Phase 5.5 のコスト再計算（`--overwrite`） |
| `scripts/extract_sparse_base.py` | Fig.9 用: dense pkl → `sparse_base.pkl` |
| `scripts/generate_synthetic_scaling.py` | Fig.9 用: `job-ceb-2-q{N}` の生成（`--queries N --freq-suffix _24_mono`、seed=0） |

**Phase ごとに必要なモジュール**
| 区分 | ファイル |
|---|---|
| 共通（`run_experiment_normal.py` の import 時に必ず読まれる） | `config/{__init__,settings}.py`、`core/{__init__,io_loaders,small_test_schema_provider,sparse_structures,time_dependent_optimizer}.py`、`src/__init__.py`、`src/core/{__init__,models,query_manager,query_parser}.py`、`src/optimization/{__init__,base,factory,normal,bigsubs,frequency,utility,utility_capacity}.py`、`src/utils/{__init__,legacy}.py`、`utils/{__init__,postgres_executor}.py` |
| Phase 2（パース） | 上記に加えて `mv_generation/{__init__,original_sql_join_extractor,enhanced_mv_generator,comma_join_rewriter,simple_mv_sql_generator}.py`、`src/rewrite/{__init__,join_graph,mv_generator,query_rewriter,schema,schema_provider,sql_parser}.py` |
| Phase 3 | `src/core/parse_exporter.py` |
| Phase 4 | `migration/{__init__,enumerate_simple_migration_plan}.py` |
| Phase 5 | `migration/sampling_migration_cost_calculator_high.py`（job-ceb-2: `--sampling-rate high`）、`migration/sampling_migration_cost_calculator.py`（Redbench: low） |
| Phase 6 Proposed | `core/cf_pruner.py`、`core/local_ilp_optimizer.py`、`core/workload_summary_tree.py`、`core/time_dependent_optimizer.py` |
| Phase 6 Static | `core/utility_v2.py`（`--static-algorithm utility`）。`src/optimization/normal.py` は import されるだけで実行されない |
| Phase 6 Adapt | `core/two_step_optimizer.py`、`core/time_dependent_optimizer.py` |
| Phase 7 | 追加 import なし（`04_migration/<set>/simple_migration_plans.json` を読む） |
| Phase 8 | `src/rewrite/query_rewriter.py`、`src/core/models.py` |
| Phase 9 | `benchmark/{__init__,time_dependent_query_executor}.py` |

注意:
- `src/optimization/{bigsubs,frequency,utility,utility_capacity}.py` は `factory.py` が import するため必要だが、論文の実験では実行されない。
- `qp_class.pkl` の unpickle には `src.core.query_parser` / `query_manager` / `models` のクラス定義が必要。モジュールのパスや名前を変えると、既存の pkl が読めなくなる。

### 3.5 実行シェルスクリプト（`scripts/shell/`）

| 実験 | スクリプト | 主な引数（結果 JSON で確認した実際の条件） | 現状との差 |
|---|---|---|---|
| 前処理 job-ceb-2 | `run_ex0_job-ceb.sh` | Phase 1〜5（`--use-sampling --sampling-rate high`）→ recalc | 出力からは high / low を判別できない（スクリプトの記述を信じるしかない） |
| 前処理 Redbench | `run_ex0_redbench.sh` | 同上（sampling low） | |
| Fig.7（ex1_1） | `run_ex1_1-ceb.sh` | `--phase post-opt --query-set job-ceb-2 --exp-suffix _24_{2_10,mono,peak} --b-max 500 --recalc --use-docker --ease`。dynamic は `--use-pruning`、static は `--static-timestep average --static-algorithm utility`、adaptive は `--window-size 4 --freq-weight linear`。Redbench は `_2h_x2_50x` | ⚠ **dynamic / static の suffix が `_rand`、Redbench が `_10x` になっており、論文の結果と一致しない** |
| Table 2（ex3） | `run_ex3.sh` | dynamic をプルーニングなしで実行 → `_wo` にリネーム | 出力先 `ex3/` と実物の `ex3_500M_ok/` は手作業で移動 |
| Fig.10（ex2） | `run_ex2_redbench_robust.sh` | `--phase 9 --benchmark-mode {dynamic,static} --exp-suffix _2h_x2_50x --noise-ratio 0.05..0.50 --ease` | ブロックの大半がコメントアウトされている（最後に static ノイズを実行した状態）。ex2/ から ex2_500M_ok/ へは手作業で移動 |
| Fig.8（ex1_3） | `run_ex1_3.sh` | `--phase 6`、T = 12..48、`--use-pruning --pruning-parallel` → `_wp`、プルーニングなし → `_wo`（24 h タイムアウト） | 出力先 `job-ceb-2/` から `result_scaling_time_ok/` へは手作業で移動 |
| Fig.11（ex4） | `run_ex4.sh` | B_max をループ、3 手法を `post-opt` で実行 → `ex4/b${BMAX}` | 現在は `_24_peak`、1000〜3000 の設定。cycle / mono / b500 は編集前の状態で実行された。出力先 `ex4/` → `ex4_ok_*` は手作業で移動（b500 は result_500M_ok からのコピー） |
| Fig.9 w/ pruning | `run_scaling_pruning.sh` | `--phase 6 --use-pruning --pruning-parallel --pruning-workers 16 --b-max 500 --recalc` | 現在は `QUERY_COUNTS=(60000 80000 100000)`。`_wp` へのリネームは手作業 |
| Fig.9 w/o pruning | `run_scaling_nopruning.sh` | `--phase 6`（プルーニングなし）、24 h タイムアウト | |
| Fig.9 Static | **スクリプトなし** | `--optimization-mode static --static-timestep average --static-algorithm utility --exp-suffix _24_mono --b-max 500`（JSON から推定） | ⚠ 実行手順が残っていない |

### 3.6 図表生成スクリプト

§1 の表に記載した 9 本:
- `progress/ex1_1/plot_timestep_time_static_init.py`
- `progress/ex1_1/plot_timestep_time_ex2_static_init.py`
- `progress/scaling_timestep/plot_timestep.py`
- `progress/scaling_pruning/plot_opt_time_query_scaling.py`
- `progress/ex3_500M/generate_table3.py`
- `time_dependent_output/ex2_500M_ok/plot_noise.py`
- `progress/ex4/plot_capacity_all.py`
- `01_queries/job-ceb-2/plot_frequency_patterns.py`
- `01_queries/Redbench_synthetic/plot_frequency_total.py`

本文の数値の生成: `progress/gen_data_summary.py`

---

## 4. 実験自体には不要だが補助となるファイル

| 区分 | ファイル | 用途 |
|---|---|---|
| 数値の根拠・考察メモ | `progress/2026-08-09_experiment_data_summary.md`、`progress/2026-07-13_ex2_500M_prediction_accuracy.md`、`progress/2026-07-13_ex2_500M_timestep_time.md`、`progress/2026-07-13_optimization_time_query_scaling.md`、`progress/scaling_timestep/2026-07-13_timestep_scaling.md`、`progress/ex3_500M/2026-07-13_ex3_500M_pruning_table.md` | 各図の定義（使うフィールド）と考察。論文執筆時の一次資料 |
| 図表の数値 | `progress/scaling_timestep/timestep.json`、`progress/ex3_500M/table3_markdown.md` | 図表の値のテキスト版 |
| 実装の経緯 | `progress/2026-06-18_*.md`、`2026-06-19_sparse_scalability.md`、`2026-06-25_parallel_pruning_shm.md`、`2026-06-26_seq_vs_parallel_results.md`、`2026-07-02_ease_mode_noise_support.md` | sparse 化、SHM 並列化、ease モード、noise 対応の設計と検証 |
| 実行ログ | `progress/scaling_pruning/{q*.log,nopruning_*.log,nopruning.console.log,summary.txt,results.md}`、`time_dependent_output/ex1_1/log/`、`time_dependent_output/ex1_3/log/` | Fig.9 の DNF と時間内訳の証跡、Fig.8 のログ |
| 定式化の解説 | `core/objective_function.md`、`small_docs/explain/{time_dependent_optimizer,io_loaders,constraint}.md`、`small_docs/plans/*.md` | ILP 定式化とコードの対応（論文の Sec.3 と照合する際に使う） |
| 手順書 | `README.md`（Phase 別の手順、Redbench 付録）、`AGENT.md`、`scripts/DATABASE_SETUP.md` | 再現手順の説明（リファクタリング後に要更新） |
| 最適化結果の中身確認 | `utils/inspect_pickle.py` | pkl の中身を JSON に出力する |
| 回帰テスト | `tests/test_pruning.py`、`pytest.ini` | CF Pruning の簡易テスト |
| ワークロード生成（上流） | `Redbench/`（ワークロード生成器）、`scripts/generate_queryset_from_workload_csv.py`、`scripts/normalize_queryset_table_versions.py`、`scripts/merge_query_folders.py`、`scripts/merge_query_folders_sum.py` | Redbench_synthetic の作成（workload.csv → クエリセット → 正規化 → cluster 53 と 55 の結合）。**10x / 50x へのスケーリングと、job-ceb-2 の頻度ファイル・クエリセットの生成スクリプトは見つからなかった**（`description` からは「cluster 53 and 55 combined」「x5 of _2h_x2_10x」といった手作業の加工と読める） |
| 別図（論文未使用） | `progress/ex1_1/timestep_time_*.pdf`（static_init でない版）、`progress/ex4/capacity_bar{,_mono,_peak}.pdf`、`progress/scaling_pruning/{plot_scaling,plot_compare,plot_three,plot_seq_vs_parallel,plot_proposed_vs_static,plot_total_stacked*,plot_timestep_time,generate_figures}.py` とその出力 | 旧版の図、BigSubs や逐次/並列の比較図（査読対応などで使う可能性あり） |
| 可視化 | `dashboard/` | 結果閲覧用の FastAPI ダッシュボード |
| 関連資料 | `small_docs/wakuta_EDBT.{md,pdf}`、`adaptive_method_survey.{md,html}` | 先行研究（NoSQL 版）、Adapt ベースラインの設計調査 |

### 4.1 論文の実験に不要なファイル（リファクタリングで整理できる候補）

- **論文の経路では実行されないが、静的には到達可能なもの**: `migration/{actual_cost,neurocard,deepdb}_migration_cost_calculator.py`、`migration/deepdb_estimator.py`、`migration/simple_migration_cost_calculator.py`、`src/estimation/*`、`src/rewrite/enhanced_mv_generator.py`（`generate_sql=True` の場合のみ使う）
- **どこからも参照されないもの**: `benchmark/time_dependent_query_executor copy.py`、`core/two_step_optimizer copy.py`、`core/utility_pruner copy.py`、`core/utility_pruner{,_iterative,_iterative_helpers,_simple}.py`、`src/core/{query_manager,query_parser}_distinct.py`、`src/rewrite/{advanced_rewriter,query_graph}.py`、`src/database/`、`src/benchmark/`、`src/utils/{file_utils,logging_utils,validators}.py`、トップレベルの `rewrite/`、`utils/{analyze_benchmark_results,csv_exporter(構文エラーあり),plot_benchmark}.py`、`scripts/run_utility_{benchmark,optimization}.py`、`scripts/setup_imdb.py`、`scripts/scratch/`、`scripts/progress/`、`scripts/shell/` の上記以外（`run_ex0_job.sh`、`run_ex1_1.sh`、`run_ex1_2_*.sh`、`run_ex4_redbench.sh`、`run_renew_adapt.sh`、`run_48.sh`）
- **ルートの設定・SQL**: `config.yaml`（参照は `enumerate_simple_migration_plan.py` の `__main__` にある古いパスだけ）、`config/experiments/*.yaml`、`00_setup.sql`、`insert_queries.sql`、`query_groups.json`（いずれもコードからの参照なし）
- **その他**: `experiments/`、`garvage_can/`、`archive/`（`archive/data/` は除く）、`htmlcov/`、`.coverage`、`figure/`

---

## 5. リファクタリング時の注意点（再現性リスク）

1. **`run_ex1_1-ceb.sh` の suffix が論文の結果と合っていない。** dynamic / static が `_24_*_rand`、Redbench が `_2h_x2_10x` になっている。論文の結果は `_24_*` と `_2h_x2_50x` で得られたもので、頻度の完全一致照合でも確認した。
2. **結果フォルダ（`*_ok`）は手作業で移動・リネームしたもの。** シェルの出力先（`time_dependent_output/<set>/`、`ex3/`、`ex4/b*`）と実物のパスが一致しない。`_wp` / `_wo` / `_seq` のリネームも一部が手作業。
3. **Dockerfile の COPY 元が存在しない**（`./data/` → `archive/data/`）。
4. **論文に必須のファイルが git 管理外にある。** `.gitignore` の `01_queries/job-ceb-2/`、`03_parsed/`、`time_dependent_output/`、`*.log` が該当し、対象は job-ceb-2 のクエリと頻度、全結果 JSON、`plot_noise.py`（Fig.10）、`plot_frequency_patterns.py`（Fig.5）。提出用には別途アーカイブするか、追跡対象に移す必要がある。
5. **Phase 7/8 の中間生成物は上書きされている**（§2.8）。
6. **結果を出した後にコードが変わっている。** Fig.7/Table 2 の dynamic 結果は 6/8〜6/14 に生成されたが、その後 6/25 に sparse 対応、6/29 に SHM 並列化が入った。メモでは dense 経路はバイト同一、並列と逐次で有望集合は同一とされている。ただし、Gurobi のスレッド数やモデルを変えるとタイブレークで有望 MV 集合が変わりうる。リファクタリング後は `pruning_info.promising_candidates` が一致するかで回帰を確認するとよい。
7. **一部の実行条件が結果 JSON に記録されていない。** Adapt の `--freq-weight`（シェルと論文の記述からは linear）、Phase 5 の sampling high / low、`--pruning-parallel` の有無は JSON からは判別できない。今後は結果 JSON に引数を保存するのが望ましい。
8. `--phase 0` は存在しないメソッド `phase0_setup` を呼んでいる（実行すると AttributeError になる）。

---

## 6. 論文本文とデータの整合チェック（参考）

| 論文の記述 | データ | 判定 |
|---|---|---|
| Abstract / Intro「Static 比で最大 24.6% 削減」「Adapt 比で最大 45.6% 削減」 | 総実行時間の削減率は Static 比 2.4〜63.3%、Adapt 比 3.7〜87.4%（ex1 / ex2 / ex4 の全条件）。時刻別の最大値は Static 比 17.7%、Adapt 比 50.7% | ⚠ **一致する値が見つからない**（旧版の数値が残っている可能性） |
| 5.2.1「Redbench で Adapt 比 87.4%、Static 比 62.8% 削減」 | 87.4% は一致。62.8% は **Static の初期構築を除いた**値で、含めると 63.3%。Fig.7 と Fig.10/11 は初期構築を含めている | ⚠ 定義の揃え方を確認 |
| 5.1.2「Redbench synthetic は 2,294 クエリ」 | 2,284 クエリ（`parse_summary.json`、SQL の本数、頻度ファイルのキー数がすべて 2,284） | ⚠ 誤記の可能性 |
| Fig.8 のキャプション「2500 queries」 | 2,515 クエリ | 概数表記なら問題なし |
| 2.03×（Cycles t13）、1.78×（Growth t15）、最大 1.13×（Evolution） | 一致 | ✓ |
| Table 2 の全数値、93〜94% 削減、劣化 0.07% 未満、−4.5〜0.4% | 一致 | ✓ |
| 1.22×（12 TS）、6.35×（42 TS） | 一致 | ✓ |
| 40k で 20.8 h、100k で 4.2 h、24〜26 倍、Static 比 1.7〜2.5 倍 | 20.77 h、4.18 h、23.8〜25.9 倍、1.67〜2.47 倍 | ✓ |
| recall 55% 以上で最速、50% で Adapt より遅い | 55%: 405,050 < 414,284（Adapt）、50%: 435,607 > 414,284 | ✓ |
