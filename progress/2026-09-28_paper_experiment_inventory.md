# Inventory of the experiment files for the paper (EDBT 2026, "Schema Optimization for Time-Dependent Workloads")

Created: 2026-09-28. Purpose: before refactoring the repository for the submission, identify
the result data behind every figure and table of the paper, the files needed to reproduce
them, and auxiliary files.
**The survey itself did not modify any file in the repository** (only this file was created;
`__pycache__` writing was disabled during the checks).

Method:
- Read the input paths of every plotting script and matched the contents of the result JSONs
  (algorithm name, `storage_budget`, number of candidates, times) against the numbers in the paper.
- Matched the per-time-step, per-query frequencies recorded in the benchmark results exactly
  against `01_queries/*/frequency_time_dependent*.json` to identify the frequency files actually used.
- Identified identical copies by md5.
- Traced code dependencies from the entry points via the AST, and confirmed them with runtime imports (`-B`).

## Status update (after the follow-up work on 2026-09-28)

- `paper/` now contains shell scripts that reproduce every experiment into `time_dependent_output/rq*/`
  with the settings identified below (`run_ex1_1-ceb.sh` issue of §5.1 does not apply to them).
- `paper_figures/` generates exactly the figures/tables of the paper from `rq*/`; checked to be
  pixel-identical to the existing paper figures when fed with the original data.
- `docker/` + the fixed `Dockerfile` recreate the DB container (§5.3 fixed); PostgreSQL is **18.4**
  (the paper says 18.3).
- Code changes after the results (§5.6): for Evolution/500MB and q20000, results before and after the
  changes have identical promising sets, objective values and selected MVs for all 24 time steps.
- The LaTeX of Table 2 now uses `table*` and `\label{table:ex3_1}`.

---

## 0. Summary

- The paper has **8 figures + 1 table + numbers in the text**. The corresponding result JSONs are
  **152 files**, or **128 files** without duplicate copies.
- The preprocessing inputs (`01_queries/job-ceb-2/`, `02_json`, `03_parsed`, `04_migration`) and
  `time_dependent_output/` are **all untracked by git**. The scripts generating Fig. 10 and Fig. 5 are
  untracked as well.
- The code that actually produced the paper results consists of **53 files** (§3.4).
- Among the corresponding shell scripts, **`run_ex1_1-ceb.sh` does not reproduce the paper results as is**
  (it points to `_rand` / `_10x`). Some outputs were also renamed by hand, and some runs have no script (§5).
- The COPY source `./data/` of the `Dockerfile` was moved to `archive/data/`, so **`docker build` fails as is**.
- Among the numbers in the text, **"24.6%" and "45.6%" in the abstract / introduction do not match any
  current result** (§6).

---

## 1. Mapping between the figures/tables of the paper and the result data

| Paper | Content | Figure file (used in the paper) | Generating script | Input data |
|---|---|---|---|---|
| Fig. 5 | Frequency patterns (Cycles / Evolution / Growth) | `01_queries/job-ceb-2/frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf` | `01_queries/job-ceb-2/plot_frequency_patterns.py` ⚠ untracked | `01_queries/job-ceb-2/frequency_time_dependent_{24_2_10,24_mono,24_peak}.json` |
| Fig. 6 | Total execution count of Redbench | `01_queries/Redbench_synthetic/plots/frequency_pattern_Redbench.pdf` | `01_queries/Redbench_synthetic/plot_frequency_total.py` | `01_queries/Redbench_synthetic/frequency_time_dependent_2h_x2_50x.json` |
| Fig. 7 | Execution time per time step (4 panels) | `progress/ex1_1/timestep_time_{24_2_10,24_mono,24_peak}_static_init.pdf`, `progress/ex1_1/timestep_time_ex2_500M_static_init.pdf` | `progress/ex1_1/plot_timestep_time_static_init.py`, `progress/ex1_1/plot_timestep_time_ex2_static_init.py` | `time_dependent_output/job-ceb-2/result_500M_ok/`, `time_dependent_output/ex2_500M_ok/` |
| Fig. 8 | Optimization time vs. number of time steps | `progress/scaling_timestep/timestep_bar.pdf` | `progress/scaling_timestep/plot_timestep.py` | `time_dependent_output/job-ceb-2/result_scaling_time_ok/` |
| Fig. 9 | Optimization time vs. number of queries | `progress/scaling_pruning/opt_time_query_scaling.pdf` | `progress/scaling_pruning/plot_opt_time_query_scaling.py` | `time_dependent_output/job-ceb-2-q{20000..100000}/` |
| Table 2 | With vs. without pruning | `progress/ex3_500M/table3.tex` | `progress/ex3_500M/generate_table3.py` | `time_dependent_output/ex3_500M_ok/` |
| Fig. 10 | Robustness against prediction recall | `time_dependent_output/ex2_500M_ok/ex2_500M_noise.pdf` | `time_dependent_output/ex2_500M_ok/plot_noise.py` ⚠ untracked | `time_dependent_output/ex2_500M_ok/` |
| Fig. 11 | Storage constraint vs. total execution time (3 panels) | `progress/ex4/capacity_bar_all.pdf` | `progress/ex4/plot_capacity_all.py` | `time_dependent_output/ex4_ok_{cycle,mono,peak}/b{500,1000,1500,2000}/` |
| Numbers in the text | 2.03×, 1.78×, 87.4%, 20.8 h, ... | `progress/2026-08-09_experiment_data_summary.md` | `progress/gen_data_summary.py` | same as above |

Notes:
- **Fig. 7 uses the `_static_init` variants.** They add the initial MV build time of Static to t=1;
  the Static value of Cycles at t=1 is 19,494 s (18,070 s without it), which matches the paper figure.
  The `timestep_time_*.pdf` files without `_static_init` are not used in the paper.
- **Fig. 11 uses `capacity_bar_all.pdf` (3 panels).** `capacity_bar{,_mono,_peak}.pdf` are older single-panel versions.
- All plotting scripts **assume they are run from the project root** (relative paths). The exception is
  `plot_noise.py`, which resolves paths relative to its own directory (`DIR = Path(__file__).parent`).

---

## 2. Required result files (in `time_dependent_output/`)

Legend: ★ file read directly by a figure/table / ○ the corresponding optimization result (provenance;
not plotted, but it is the input of Phases 7–9 and documents the run settings)

### 2.1 Fig. 7 (3 JOB+CEB patterns): `time_dependent_output/job-ceb-2/result_500M_ok/` (18 files)

`{fq}` = `24_2_10` (Cycles) / `24_mono` (Evolution) / `24_peak` (Growth)

| Method | ★ Benchmark result | ○ Optimization result |
|---|---|---|
| Proposed | `benchmark_results_dynamic_{fq}.json` | `td_mv_optimization_result_{fq}.json` |
| Adapt | `benchmark_results_adaptive_w4_{fq}.json` | `adaptive_mv_optimization_result_w4_{fq}.json` |
| Static | `benchmark_results_static_{fq}.json` | `static_mv_optimization_result_{fq}.json` |

- Field used: `timestep_results[t].total_time`. For Static, `initial_mv_creation_time` is added to t=1.
- Run settings (checked in the JSONs): B_max = 500 MB (`storage_budget` = 524,288,000), T = 24,
  26,312 candidates → 1,656 / 1,772 / 1,648 after pruning, Static `algorithm` = `static_utility` / `timestep` = `average`.
- **The 18 files in `time_dependent_output/ex1_1_500M_ok/` are byte-identical copies of the above** (md5).
  The plotting scripts read `result_500M_ok`.
- Files in the same directory not used in the paper: `*_wo.json` (6 adaptive), `*peloton*` (4),
  `*static_bigsubs*` (6), `*.pdf` (6).

### 2.2 Fig. 7 (Redbench panel) and Fig. 10: `time_dependent_output/ex2_500M_ok/` (26 files + script)

| Kind | Files |
|---|---|
| ★ Proposed | `benchmark_results_dynamic_2h_x2_50x.json` (no noise = recall 100%), `benchmark_results_dynamic_2h_x2_50x_noise{5,10,…,50}.json` (10 files) |
| ★ Static | `benchmark_results_static_2h_x2_50x.json`, `benchmark_results_static_2h_x2_50x_noise{5,…,50}.json` (10 files) |
| ★ Adapt | `benchmark_results_adaptive_w4_2h_x2_50x.json` (only one; unaffected by noise) |
| ○ Optimization results | `td_mv_optimization_result_2h_x2_50x.json` (23,696 → 2,557 candidates), `static_mv_optimization_result_2h_x2_50x.json`, `adaptive_mv_optimization_result_w4_2h_x2_50x.json` |
| Figure generation | `plot_noise.py` → `ex2_500M_noise.pdf` / `.png` |

- recall = 100 − noise (%). Fig. 10 uses `summary.total_benchmark_time`.
- The noisy results re-ran only Phase 9 with `--noise-ratio X --ease`; they share the noise-free optimization results.

### 2.3 Table 2: `time_dependent_output/ex3_500M_ok/` (12 files)

| Kind | Files |
|---|---|
| With pruning | `td_mv_optimization_result_{fq}.json`, `benchmark_results_dynamic_{fq}.json` ← **byte-identical copies of `result_500M_ok`** |
| Without pruning | `td_mv_optimization_result_{fq}_wo.json`, `benchmark_results_dynamic_{fq}_wo.json` (only these 6 files are unique) |

- Column definitions: optimization time = `pruning_time_sec + solve_time_sec`, total execution time =
  `summary.total_benchmark_time`, objective value = −`objective`/1000.

### 2.4 Fig. 8: `time_dependent_output/job-ceb-2/result_scaling_time_ok/` (12 files)

- `td_mv_optimization_result_{12,18,24,30,36,42}_mono_{wp,wo}.json`. The y-axis is `phase_time_sec`.
- `*_48_mono_{wp,wo}.json` also exist, but the figure in the paper stops at 42.
- Logs: `time_dependent_output/ex1_3/log/log_dynamic_*_mono_{wp,wo}.txt`.

### 2.5 Fig. 9: `time_dependent_output/job-ceb-2-q{N}/` (12 files)

| N | ★ Static | ★ Proposed (w/ pruning) | ★ Proposed (w/o pruning) |
|---|---|---|---|
| 20000, 40000 | `static_mv_optimization_result_24_mono.json` | `td_mv_optimization_result_24_mono_wp.json` | `td_mv_optimization_result_24_mono.json` |
| 60000, 80000, 100000 | same | same | none (DNF) |

- Static uses `execution_time`, Proposed uses `phase_time_sec`.
- Evidence for DNF: `progress/scaling_pruning/nopruning_q60000.log` ends with Gurobi still solving at
  82,276 s (24 h timeout). 80k / 100k were not run because of the early stop.
- Not used in the paper: `*_seq.json` (sequential pruning; same objective and promising set as `_wp`),
  `static_bigsubs_*`, `job-ceb-2-q10000/`, `job-ceb-2-x2/`.

### 2.6 Fig. 11: `time_dependent_output/ex4_ok_{cycle,mono,peak}/b{500,1000,1500,2000}/` (72 files)

Each directory contains these 6 files (`{fq}` = cycle→`24_2_10`, mono→`24_mono`, peak→`24_peak`):
- ★ `benchmark_results_{dynamic,static,adaptive_w4}_{fq}.json` (`summary.total_benchmark_time`; Static includes the initial build)
- ○ `td_mv_optimization_result_{fq}.json`, `static_mv_optimization_result_{fq}.json`, `adaptive_mv_optimization_result_w4_{fq}.json`

Notes:
- **The 18 files in `b500/` are byte-identical copies of `result_500M_ok`.**
- `ex4_ok_peak/b2500/` and `b3000/` are not used in the paper.

### 2.7 Totals

| Directory | Required files | Unique data |
|---|---:|---:|
| job-ceb-2/result_500M_ok | 18 | 18 |
| ex2_500M_ok | 26 | 26 |
| ex3_500M_ok | 12 | 6 |
| job-ceb-2/result_scaling_time_ok | 12 | 12 |
| job-ceb-2-q{20k..100k} | 12 | 12 |
| ex4_ok_{cycle,mono,peak}/b500..b2000 | 72 | 54 |
| **Total** | **152** | **128** |

### 2.8 Contents of `time_dependent_output/` not used in the paper (for reference)

`cluster_*` (6), `job/`, `job_old/`, `job_plus/`, `job_real/`, `ex1_1/` (old job set, 100 MB setting),
`ex1_2/`, `ex2/`, `ex3/` (empty log directories), `ex4_old/`, `ex4_redbench/`, `Redbench_synthetic/result_*` (11),
`job-ceb-2/td_mv_optimization_result_{24,48}_mono.json` (old outputs directly under the directory).

> ⚠ `timestep_*.sql`, `static_initial_mvs.sql` and `jobs/` directly under `time_dependent_output/<set>/`
> (intermediates of Phases 7/8) are **overwritten by every run**. The current ones belong to the last run
> (e.g. Aug 15 for `job-ceb-2` = ex4 peak, b3000) and **do not correspond to the paper results**.
> To reproduce, regenerate Phases 7/8 from the corresponding optimization result.

---

## 3. Files needed to obtain the results

### 3.1 Experiment pipeline (overview)

```
[Preprocessing] Phase1 EXPLAIN → Phase2 parse → Phase3 annotate → Phase4 plans → Phase5 costs (sampling) → recalc
                (scripts/shell/run_ex0_job-ceb.sh / run_ex0_redbench.sh)
[Main]          Phase6 optimization (dynamic / static / adaptive) → Phase7 MV SQL → Phase8 rewrite → Phase9 benchmark (--ease)
                (--phase post-opt runs 6–9 at once; the scalability experiments use only --phase 6 and need no DB)
```

### 3.2 Environment

| File | Purpose | Status |
|---|---|---|
| `Dockerfile` | PostgreSQL + IMDB (shared_buffers=2GB, work_mem=128MB, max_locks_per_transaction=256) | ⚠ `COPY ./data/schema.sql` and `./data/setup.sql` are broken (the files are in `archive/data/`) |
| `archive/data/schema.sql`, `archive/data/setup.sql` | DB schema and load SQL copied by the Dockerfile | moved under archive/ |
| `requirements.txt`, `pyproject.toml`, `uv.lock` | Python 3.12 dependencies (gurobipy, psycopg2, sqlparse, numpy, matplotlib, ...) | |
| `gurobi.lic` / `.env` (`GRB_LICENSE_FILE`, `DB*`) | Gurobi license and DB connection | ⚠ must not be published |
| `config/default.yaml` | Loaded automatically by `Settings()` (unless `CONFIG_PATH` is set): DB connection, timeout | the code comment "config.yaml is not used" is misleading; this file is used |
| `config/__init__.py`, `config/settings.py` | Configuration loading | |

### 3.3 Input data (all untracked by git; only the Redbench SQL files are tracked)

| Query set | 01_queries | 02_json | 03_parsed | 04_migration |
|---|---|---|---|---|
| `job-ceb-2` (2,515 queries, 26,312 candidates) | 2,515 `*.sql` + `frequency_time_dependent_{24_2_10,24_mono,24_peak}.json` (Fig. 5/7/11, Table 2) + `_{12,18,24,30,36,42}_mono.json` (Fig. 8) | 2,515 `*.json` (51 MB) | `qp_class.pkl` (2.9 GB), `parse_summary.json`, `sparse_base.pkl` (136 MB; for generating the synthetic sets) | `simple_migration_plans.json`, `simple_migration_costs.json` (recalculated, `calc_method=pickle_recursive_v2`) |
| `Redbench_synthetic` (2,284 queries, 23,696 candidates) | 2,284 `*.sql` + `frequency_time_dependent_2h_x2_50x.json` | 2,284 `*.json` | `qp_class.pkl` (2.2 GB), `parse_summary.json` | same |
| `job-ceb-2-q{20000,40000,60000,80000,100000}` (synthetic) | `frequency_time_dependent_24_mono.json` | none | `qp_class.pkl` (SparseQP format, 2.1–13 GB) | `simple_migration_costs.json` |

The frequency files used were determined by exact matching against the frequencies in the benchmark results:
- All job-ceb-2 experiments use the versions **without `_rand`** (`_24_2_10` / `_24_mono` / `_24_peak`);
  all 24 time steps match, whereas the `_rand` versions match only 0–16 time steps.
- Redbench uses **`_2h_x2_50x`**; `_2h_x2` and `_2h_x2_10x` match 0 time steps.
- Frequency files not used in the paper: `*_rand.json` (3), `_48_mono.json`, Redbench `_2h_x2.json` and `_2h_x2_10x.json`.

### 3.4 Python code (53 files, confirmed via runtime imports)

**Entry points**
| File | Role |
|---|---|
| `scripts/run_experiment_normal.py` | Driver of all phases (`--phase 1..9 / post-opt`) |
| `scripts/recalculate_costs.py` | Phase 5.5 cost recalculation (`--overwrite`) |
| `scripts/extract_sparse_base.py` | For Fig. 9: dense pkl → `sparse_base.pkl` |
| `scripts/generate_synthetic_scaling.py` | For Fig. 9: generates `job-ceb-2-q{N}` (`--queries N --freq-suffix _24_mono`, seed=0) |

**Modules required per phase**
| Part | Files |
|---|---|
| Common (always loaded when importing `run_experiment_normal.py`) | `config/{__init__,settings}.py`, `core/{__init__,io_loaders,small_test_schema_provider,sparse_structures,time_dependent_optimizer}.py`, `src/__init__.py`, `src/core/{__init__,models,query_manager,query_parser}.py`, `src/optimization/{__init__,base,factory,normal,bigsubs,frequency,utility,utility_capacity}.py`, `src/utils/{__init__,legacy}.py`, `utils/{__init__,postgres_executor}.py` |
| Phase 2 (parsing) | in addition, `mv_generation/{__init__,original_sql_join_extractor,enhanced_mv_generator,comma_join_rewriter,simple_mv_sql_generator}.py`, `src/rewrite/{__init__,join_graph,mv_generator,query_rewriter,schema,schema_provider,sql_parser}.py` |
| Phase 3 | `src/core/parse_exporter.py` |
| Phase 4 | `migration/{__init__,enumerate_simple_migration_plan}.py` |
| Phase 5 | `migration/sampling_migration_cost_calculator_high.py` (job-ceb-2: `--sampling-rate high`), `migration/sampling_migration_cost_calculator.py` (Redbench: low) |
| Phase 6 Proposed | `core/cf_pruner.py`, `core/local_ilp_optimizer.py`, `core/workload_summary_tree.py`, `core/time_dependent_optimizer.py` |
| Phase 6 Static | `core/utility_v2.py` (`--static-algorithm utility`); `src/optimization/normal.py` is imported but not executed |
| Phase 6 Adapt | `core/two_step_optimizer.py`, `core/time_dependent_optimizer.py` |
| Phase 7 | no additional imports (reads `04_migration/<set>/simple_migration_plans.json`) |
| Phase 8 | `src/rewrite/query_rewriter.py`, `src/core/models.py` |
| Phase 9 | `benchmark/{__init__,time_dependent_query_executor}.py` |

Notes:
- `src/optimization/{bigsubs,frequency,utility,utility_capacity}.py` are needed because `factory.py` imports
  them, but they are not executed in the paper experiments.
- Unpickling `qp_class.pkl` requires the class definitions in `src.core.query_parser` / `query_manager` /
  `models`. Renaming or moving these modules breaks the existing pickles.

### 3.5 Shell scripts (`scripts/shell/`)

| Experiment | Script | Main arguments (actual settings confirmed in the result JSONs) | Difference from the current state |
|---|---|---|---|
| Preprocessing job-ceb-2 | `run_ex0_job-ceb.sh` | Phases 1–5 (`--use-sampling --sampling-rate high`) → recalc | high / low cannot be told from the outputs (relies on the script) |
| Preprocessing Redbench | `run_ex0_redbench.sh` | same (sampling low) | |
| Fig. 7 (ex1_1) | `run_ex1_1-ceb.sh` | `--phase post-opt --query-set job-ceb-2 --exp-suffix _24_{2_10,mono,peak} --b-max 500 --recalc --use-docker --ease`; dynamic `--use-pruning`, static `--static-timestep average --static-algorithm utility`, adaptive `--window-size 4 --freq-weight linear`; Redbench `_2h_x2_50x` | ⚠ **the suffixes of dynamic / static are `_rand` and Redbench is `_10x`, which does not match the paper results** |
| Table 2 (ex3) | `run_ex3.sh` | dynamic without pruning → renamed to `_wo` | output `ex3/` was moved to `ex3_500M_ok/` by hand |
| Fig. 10 (ex2) | `run_ex2_redbench_robust.sh` | `--phase 9 --benchmark-mode {dynamic,static} --exp-suffix _2h_x2_50x --noise-ratio 0.05..0.50 --ease` | most blocks are commented out (left in the state of the last static-noise run); moved from ex2/ to ex2_500M_ok/ by hand |
| Fig. 8 (ex1_3) | `run_ex1_3.sh` | `--phase 6`, T = 12..48, `--use-pruning --pruning-parallel` → `_wp`, without pruning → `_wo` (24 h timeout) | output `job-ceb-2/` was moved to `result_scaling_time_ok/` by hand |
| Fig. 11 (ex4) | `run_ex4.sh` | loops over B_max, runs the 3 methods with `post-opt` → `ex4/b${BMAX}` | currently set to `_24_peak`, 1000–3000; cycle / mono / b500 were run with earlier versions; `ex4/` → `ex4_ok_*` moved by hand (b500 copied from result_500M_ok) |
| Fig. 9 w/ pruning | `run_scaling_pruning.sh` | `--phase 6 --use-pruning --pruning-parallel --pruning-workers 16 --b-max 500 --recalc` | currently `QUERY_COUNTS=(60000 80000 100000)`; renaming to `_wp` was done by hand |
| Fig. 9 w/o pruning | `run_scaling_nopruning.sh` | `--phase 6` (no pruning), 24 h timeout | |
| Fig. 9 Static | **no script** | `--optimization-mode static --static-timestep average --static-algorithm utility --exp-suffix _24_mono --b-max 500` (inferred from the JSONs) | ⚠ no record of how it was run |

### 3.6 Figure/table generation scripts

The 9 scripts listed in §1:
- `progress/ex1_1/plot_timestep_time_static_init.py`
- `progress/ex1_1/plot_timestep_time_ex2_static_init.py`
- `progress/scaling_timestep/plot_timestep.py`
- `progress/scaling_pruning/plot_opt_time_query_scaling.py`
- `progress/ex3_500M/generate_table3.py`
- `time_dependent_output/ex2_500M_ok/plot_noise.py`
- `progress/ex4/plot_capacity_all.py`
- `01_queries/job-ceb-2/plot_frequency_patterns.py`
- `01_queries/Redbench_synthetic/plot_frequency_total.py`

Numbers in the text: `progress/gen_data_summary.py`

---

## 4. Auxiliary files (not needed to run the experiments)

| Kind | Files | Purpose |
|---|---|---|
| Evidence and discussion notes | `progress/2026-08-09_experiment_data_summary.md`, `progress/2026-07-13_ex2_500M_prediction_accuracy.md`, `progress/2026-07-13_ex2_500M_timestep_time.md`, `progress/2026-07-13_optimization_time_query_scaling.md`, `progress/scaling_timestep/2026-07-13_timestep_scaling.md`, `progress/ex3_500M/2026-07-13_ex3_500M_pruning_table.md` | Definitions of each figure (fields used) and discussion; primary material for writing the paper |
| Figure/table values | `progress/scaling_timestep/timestep.json`, `progress/ex3_500M/table3_markdown.md` | Text versions of the plotted values |
| Implementation history | `progress/2026-06-18_*.md`, `2026-06-19_sparse_scalability.md`, `2026-06-25_parallel_pruning_shm.md`, `2026-06-26_seq_vs_parallel_results.md`, `2026-07-02_ease_mode_noise_support.md` | Design and validation of the sparse version, SHM parallelization, ease mode and noise support |
| Execution logs | `progress/scaling_pruning/{q*.log,nopruning_*.log,nopruning.console.log,summary.txt,results.md}`, `time_dependent_output/ex1_1/log/`, `time_dependent_output/ex1_3/log/` | Evidence for the DNFs and time breakdown of Fig. 9, logs of Fig. 8 |
| Formulation notes | `core/objective_function.md`, `small_docs/explain/{time_dependent_optimizer,io_loaders,constraint}.md`, `small_docs/plans/*.md` | Mapping between the ILP formulation and the code (useful for checking against Section 3 of the paper) |
| Instructions | `README.md` (per-phase steps, Redbench appendix), `AGENT.md`, `scripts/DATABASE_SETUP.md` | Reproduction steps (to be updated after the refactoring) |
| Inspection | `utils/inspect_pickle.py` | Dumps the contents of a pkl as JSON |
| Regression test | `tests/test_pruning.py`, `pytest.ini` | Simple tests of CF pruning |
| Workload generation (upstream) | `Redbench/` (workload generator), `scripts/generate_queryset_from_workload_csv.py`, `scripts/normalize_queryset_table_versions.py`, `scripts/merge_query_folders.py`, `scripts/merge_query_folders_sum.py` | Creation of Redbench_synthetic (workload.csv → query set → normalization → combining clusters 53 and 55). **No script was found for the 10x / 50x scaling or for generating the job-ceb-2 query set and frequency files** (the `description` fields, e.g. "cluster 53 and 55 combined", "x5 of _2h_x2_10x", suggest manual processing) |
| Other figures (not in the paper) | `progress/ex1_1/timestep_time_*.pdf` (without static_init), `progress/ex4/capacity_bar{,_mono,_peak}.pdf`, `progress/scaling_pruning/{plot_scaling,plot_compare,plot_three,plot_seq_vs_parallel,plot_proposed_vs_static,plot_total_stacked*,plot_timestep_time,generate_figures}.py` and their outputs | Older versions of figures, comparisons with BigSubs and sequential/parallel pruning (possibly useful for the rebuttal) |
| Visualization | `dashboard/` | FastAPI dashboard for browsing results |
| Related material | `small_docs/wakuta_EDBT.{md,pdf}`, `progress/adaptive_method_survey.{md,html}` | Prior work (NoSQL version), design survey of the Adapt baseline |

### 4.1 Files not needed for the paper experiments (candidates for cleanup)

- **Statically reachable but never executed in the paper runs**: `migration/{actual_cost,neurocard,deepdb}_migration_cost_calculator.py`,
  `migration/deepdb_estimator.py`, `migration/simple_migration_cost_calculator.py`, `src/estimation/*`,
  `src/rewrite/enhanced_mv_generator.py` (only used with `generate_sql=True`)
- **Not referenced anywhere**: `benchmark/time_dependent_query_executor copy.py`, `core/two_step_optimizer copy.py`,
  `core/utility_pruner copy.py`, `core/utility_pruner{,_iterative,_iterative_helpers,_simple}.py`,
  `src/core/{query_manager,query_parser}_distinct.py`, `src/rewrite/{advanced_rewriter,query_graph}.py`,
  `src/database/`, `src/benchmark/`, `src/utils/{file_utils,logging_utils,validators}.py`, the top-level `rewrite/`,
  `utils/{analyze_benchmark_results,csv_exporter (has a syntax error),plot_benchmark}.py`,
  `scripts/run_utility_{benchmark,optimization}.py`, `scripts/setup_imdb.py`, `scripts/scratch/`, `scripts/progress/`,
  and the other files in `scripts/shell/` (`run_ex0_job.sh`, `run_ex1_1.sh`, `run_ex1_2_*.sh`, `run_ex4_redbench.sh`,
  `run_renew_adapt.sh`, `run_48.sh`)
- **Root-level configuration and SQL**: `config.yaml` (only referenced via an outdated path in the `__main__` of
  `enumerate_simple_migration_plan.py`), `config/experiments/*.yaml`, `00_setup.sql`, `insert_queries.sql`,
  `query_groups.json` (none are referenced by the code)
- **Others**: `experiments/`, `garvage_can/`, `archive/` (except `archive/data/`), `htmlcov/`, `.coverage`, `figure/`

---

## 5. Points to watch during the refactoring (reproducibility risks)

1. **The suffixes in `run_ex1_1-ceb.sh` do not match the paper results.** dynamic / static use `_24_*_rand` and
   Redbench uses `_2h_x2_10x`, whereas the paper results were obtained with `_24_*` and `_2h_x2_50x`
   (also confirmed by exact frequency matching).
2. **The result directories (`*_ok`) were moved and renamed by hand.** The output paths of the shell scripts
   (`time_dependent_output/<set>/`, `ex3/`, `ex4/b*`) do not match the actual paths; some `_wp` / `_wo` / `_seq`
   renames were also manual.
3. **The COPY source of the Dockerfile does not exist** (`./data/` → `archive/data/`).
4. **Files essential for the paper are untracked by git.** `01_queries/job-ceb-2/`, `03_parsed/`,
   `time_dependent_output/` and `*.log` in `.gitignore` cover the job-ceb-2 queries and frequencies, all result
   JSONs, `plot_noise.py` (Fig. 10) and `plot_frequency_patterns.py` (Fig. 5). For the submission they must be
   archived separately or tracked.
5. **The intermediates of Phases 7/8 have been overwritten** (§2.8).
6. **The code changed after the results were produced.** The dynamic results of Fig. 7 / Table 2 were produced on
   6/8–6/14, followed by the sparse support on 6/25 and the SHM parallelization on 6/29. According to the notes,
   the dense path is byte-identical and sequential/parallel pruning yield the same promising set. However,
   changing Gurobi's thread count or the model can change the promising MV set through tie-breaking. After the
   refactoring, check for regressions by comparing `pruning_info.promising_candidates`.
7. **Some run settings are not recorded in the result JSONs.** Adapt's `--freq-weight` (linear according to the
   scripts and the paper), the sampling rate of Phase 5 (high / low) and whether `--pruning-parallel` was used
   cannot be determined from the JSONs. Saving the arguments in the result JSONs is recommended.
8. `--phase 0` calls a method `phase0_setup` that does not exist (AttributeError when run).

---

## 6. Consistency between the text of the paper and the data (for reference)

| Statement in the paper | Data | Verdict |
|---|---|---|
| Abstract / Intro: "up to 24.6% reduction vs. Static", "up to 45.6% vs. Adapt" | Reductions of the total execution time are 2.4–63.3% vs. Static and 3.7–87.4% vs. Adapt (all settings of ex1 / ex2 / ex4); per-time-step maxima are 17.7% vs. Static and 50.7% vs. Adapt | ⚠ **no matching value found** (possibly left over from an older version) |
| 5.2.1: "Redbench: 87.4% vs. Adapt, 62.8% vs. Static" | 87.4% matches. 62.8% **excludes the initial build of Static**; including it gives 63.3%. Fig. 7 and Fig. 10/11 include it | ⚠ check which definition to use |
| 5.1.2: "Redbench synthetic has 2,294 queries" | 2,284 queries (`parse_summary.json`, number of SQL files and keys of the frequency file are all 2,284) | ⚠ possibly a typo |
| Caption of Fig. 8: "2500 queries" | 2,515 queries | fine as an approximation |
| 2.03× (Cycles t13), 1.78× (Growth t15), at most 1.13× (Evolution) | match | ✓ |
| All numbers of Table 2, 93–94% reduction, < 0.07% degradation, −4.5 to 0.4% | match | ✓ |
| 1.22× (12 TS), 6.35× (42 TS) | match | ✓ |
| 20.8 h at 40k, 4.2 h at 100k, 24–26×, 1.7–2.5× of Static | 20.77 h, 4.18 h, 23.8–25.9×, 1.67–2.47× | ✓ |
| Fastest for recall ≥ 55%, slower than Adapt at 50% | 55%: 405,050 < 414,284 (Adapt); 50%: 435,607 > 414,284 | ✓ |
