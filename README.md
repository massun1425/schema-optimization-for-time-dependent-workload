# Schema Optimization for Time-Dependent Workloads — Experiments

This repository contains the implementation and the experiment scripts of the paper
**"Schema Optimization for Time-Dependent Workloads"** (submitted to EDBT 2027).
The method selects a time series of materialized views (MVs) with an integer linear program
that maximizes the total utility of the MVs minus the migration cost between time steps, and
prunes MV candidates with a *workload summary tree*.

This README explains how to get from a fresh clone to running the experiments, and how the
repository is organized.

## Results and figures of the paper

**[`paper_results/`](paper_results/README.md) contains the results reported in the paper and
its figures and tables:**

- `paper_results/rq1/` … `paper_results/rq4/`: the result files (JSON) behind every figure and
  table, organized by research question and experiment.
- `paper_results/figures/`: the figures (PDF) and the table (LaTeX and Markdown) of the paper,
  generated from these files.

They can be regenerated without running any experiment (step 2 below).

## Names in the paper and in this repository

Several workloads, methods and parameters have different names in the paper and in the
code, the file names and the options.

| Paper | Repository |
|---|---|
| JOB + CEB queries (2,515 queries) | query set `01_queries/job-ceb-2/` |
| Cycles | `job-ceb-2` with the frequency file suffix `_24_2_10` |
| Evolution and Stagnation | `job-ceb-2` with the suffix `_24_mono`; with *T* time steps (RQ3 Exp3-2): `_{T}_mono` |
| Growth and Spikes | `job-ceb-2` with the suffix `_24_peak` |
| Group A / Group B | the two query groups of the frequency files (described in their `note` field) |
| Redbench synthetic (2,284 queries) | query set `01_queries/Redbench_synthetic/` with the suffix `_2h_x2_50x` |
| Workloads with *N* queries (RQ3 Exp3-3) | query sets `job-ceb-2-q{N}` (e.g. `job-ceb-2-q20000`) with the suffix `_24_mono` |
| Proposed (with candidate pruning) | `--optimization-mode dynamic --use-pruning`; files `td_mv_optimization_result*` and `benchmark_results_dynamic*`; tag `_wp` where both variants are stored together (RQ3 Exp3-2, Exp3-3) |
| Proposed without pruning | `--optimization-mode dynamic` without `--use-pruning`; tag `_wo` |
| Static | `--optimization-mode static --static-timestep average --static-algorithm utility`; files `static_mv_optimization_result*` and `benchmark_results_static*` |
| Adapt (*k* = 3, i.e. the last *k* + 1 = 4 time steps) | `--optimization-mode adaptive --window-size 4 --freq-weight linear`; files `adaptive_mv_optimization_result_w4*` and `benchmark_results_adaptive_w4*` |
| Storage constraint *B*<sub>max</sub> | `--b-max <MB>`; folders `b500` … `b2000` in `rq4/` |
| Prediction recall *r* % (RQ2) | noise ratio 100 − *r* %: `--noise-ratio`, files `*_noise{100−r}` (e.g. recall 90% = `_noise10`) |

The file names of the results consist of the method, the frequency file suffix and the tag,
e.g. `benchmark_results_dynamic_24_mono_wo.json` = Proposed without pruning on Evolution and
Stagnation.

## Getting started

All commands are run from the repository root.

### Requirements

- **Software.** Linux, Docker, Python 3.12, Gurobi 12.0 (an academic license is sufficient;
  the license bundled with `gurobipy` is too small for the experiments).
- **Hardware.** The paper used an HPE ProLiant DL385 Gen10 Plus with two AMD EPYC 7542
  (32 cores each) and 2 TB of memory. The PostgreSQL container is limited to 8 cores and 16 GB.
  The optimizer runs outside the container; the largest query-scaling experiment (100k queries)
  loads a 13 GB parse result.
- **Disk.** About 5 GB for the container image, about 6 GB for the preprocessing outputs of the
  two query sets, and about 36 GB for the synthetic query sets of the query-scaling experiment.

### 1. Clone and install the Python environment

```bash
git clone https://github.com/massun1425/schema-optimization-for-time-dependent-workload.git
cd schema-optimization-for-time-dependent-workload
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins the package versions used for the experiments of the paper
(Gurobi 12.0.1, NumPy, psycopg2, PyYAML, sqlparse, and Matplotlib for the figures). With [uv](https://docs.astral.sh/uv/), `uv sync`
installs the same versions from `uv.lock` (`uv sync --extra dev` adds pytest and the linters).

### 2. Check the installation (no database or Gurobi license needed)

```bash
python -m pytest tests/        # unit and regression tests; the ILP tests are skipped without a Gurobi license
bash paper_figures/make_all.sh --td-dir paper_results --out-dir /tmp/figures
diff -r paper_results/figures /tmp/figures && echo "identical to the paper"
```

The second command regenerates all figures and tables of the paper from the included results;
the output is byte-identical to `paper_results/figures/` (this is also checked by the CI).

### 3. Gurobi license

Obtain a license from [gurobi.com](https://www.gurobi.com/) and make it visible to `gurobipy`:

```bash
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

### 4. PostgreSQL container

```bash
bash docker/create_container.sh     # build -> start -> load IMDB (tens of minutes) -> verify
bash docker/verify_env.sh           # check that the container matches the paper environment
```

The container is named `mv_postgres` and listens on port 5432 (both are assumed by the code).
It runs PostgreSQL 18.4 with the server parameters of the paper (shared_buffers = 2 GB,
work_mem = 128 MB, jit = off, ...), limited to 8 cores, 16 GB of memory and 4 GB of shared memory.
The build downloads the IMDB data of the Join Order Benchmark (about 1.2 GB).
See [docker/README.md](docker/README.md) for details.

### 5. Preprocessing (needs the database)

```bash
bash paper_scripts/00_prepare.sh
```

For each query set (`job-ceb-2`, `Redbench_synthetic`) this runs EXPLAIN (Phase 1), plan parsing
and MV candidate enumeration (Phases 2–3), migration plan enumeration (Phase 4), sampling-based
cost estimation (Phase 5), and the cost recalculation (Phase 5.5). It writes `02_json/`,
`03_parsed/` and `04_migration/`. Query sets whose outputs already exist are skipped.

### 6. A first, short experiment

```bash
TIMESTEPS=12 bash paper_scripts/rq3_exp3_2_timestep_scaling.sh
```

This runs only the optimization (no database) for one point of RQ3 Exp3-2 (job-ceb-2, T = 12, with
and without pruning), which took about 15 minutes in the paper. The results are written to
`time_dependent_output/rq3/exp3_2/` and can be compared with `paper_results/rq3/exp3_2/`.
Because step 5 re-estimates the migration costs by sampling (and EXPLAIN estimates can change
between runs), the selected MVs and the objective value may differ slightly from the paper;
the run times depend on the machine.

### 7. All experiments

| Experiment | Script | Output (`time_dependent_output/`) | Approx. run time |
|---|---|---|---|
| RQ1 Exp1-1 | `paper_scripts/rq1_exp1_1_timestep_time.sh` | `rq1/exp1_1/` | ~4.5 days |
| RQ2 | `paper_scripts/rq2_prediction_recall.sh` | `rq2/` | ~2 days |
| RQ3 Exp3-1 | `paper_scripts/rq3_exp3_1_pruning.sh` | `rq3/exp3_1/` | ~1.5 days |
| RQ3 Exp3-2 | `paper_scripts/rq3_exp3_2_timestep_scaling.sh` | `rq3/exp3_2/` | ~5 hours |
| RQ3 Exp3-3 | `paper_scripts/rq3_exp3_3_query_scaling.sh` | `rq3/exp3_3/` | ~3 days |
| RQ4 | `paper_scripts/rq4_capacity.sh` | `rq4/` | ~12 days |

Run all of them in dependency order with:

```bash
DRY_RUN=1 bash paper_scripts/run_all.sh                          # print the commands only
nohup bash paper_scripts/run_all.sh > paper_run_all.log 2>&1 &   # run everything
```

- Run times are estimates from the original runs (about 11 hours per benchmark run on
  job-ceb-2 and 2–3 hours on Redbench). The optimization without pruning in the scalability
  experiments is stopped after 24 hours and reported as DNF, as in the paper.
- RQ2, RQ3 Exp3-1 and RQ4 reuse the results of RQ1 Exp1-1 that have identical settings, so
  `run_all.sh` runs it first.
- Runs whose results exist are skipped; re-running a script resumes it.
- Subsets can be run with environment variables, e.g.
  `SUFFIXES="_24_mono" CAPS="1000" bash paper_scripts/rq4_capacity.sh`.

The exact settings of every experiment (methods, flags, storage constraints, output layout)
are documented in [paper_scripts/README.md](paper_scripts/README.md).

### 8. Figures and tables

```bash
bash paper_figures/make_all.sh                            # from your own runs (time_dependent_output/rq*/)
bash paper_figures/make_all.sh --td-dir paper_results     # from the results reported in the paper
```

Both write the figures (PDF) and the table (LaTeX and Markdown) to `paper_figures/output/`:

| Experiment | Output |
|---|---|
| Workload setup | `setup_frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf`, `setup_redbench_total_count.pdf` |
| RQ1 Exp1-1 | `rq1_exp1_1_timestep_time_{cycles,evolution_and_stagnation,growth_and_spikes,redbench_synthetic}.pdf` |
| RQ2 | `rq2_prediction_recall.pdf` |
| RQ3 Exp3-1 | `rq3_exp3_1_pruning.tex`, `rq3_exp3_1_pruning.md` |
| RQ3 Exp3-2 | `rq3_exp3_2_timestep_scaling.pdf` |
| RQ3 Exp3-3 | `rq3_exp3_3_query_scaling.pdf` |
| RQ4 | `rq4_capacity.pdf` |

Execution times measured on a different machine will differ from the paper. For given
preprocessing outputs (`03_parsed/`, `04_migration/`) and Gurobi configuration, the MVs selected
by the optimizer (promising candidates, objective value and schedule) are deterministic.

## Repository layout

### In the repository

| Path | Content |
|---|---|
| `scripts/run_experiment_normal.py` | Experiment driver (Phases 1–9, see [Reference](#reference-experiment-pipeline)) |
| `scripts/recalculate_costs.py` | Cost recalculation (Phase 5.5) |
| `scripts/extract_sparse_base.py`, `scripts/generate_synthetic_scaling.py` | Construction of the synthetic query sets of RQ3 Exp3-3 |
| `scripts/redbench_synthesizer/` | Conversion of Redbench workloads into query sets ([README](scripts/redbench_synthesizer/README.md)); not needed to reproduce the paper |
| `core/` | Time-dependent ILP optimizer, candidate pruning (workload summary tree), Static and Adapt baselines |
| `src/` | Query plan parsing and MV candidates (`core/`), static ILP optimizers (`optimization/`), query rewriting (`rewrite/`) |
| `migration/` | Migration plans (Phase 4) and cost estimation by sampling (Phase 5) |
| `mv_generation/` | MV definition SQL (including join conditions recovered from the original queries) |
| `benchmark/` | Benchmark executor (Phase 9) |
| `config/` | Settings (`default.yaml`: database connection and defaults) |
| `utils/` | PostgreSQL access (directly or through the Docker container) |
| `01_queries/` | Input query sets and time-dependent query frequencies (see below) |
| `paper_scripts/` | Shell scripts that run every experiment of the paper ([README](paper_scripts/README.md)) |
| `paper_figures/` | Scripts that turn the results into the figures and tables of the paper ([README](paper_figures/README.md)) |
| `paper_results/` | **The results reported in the paper (`rq*/`) and its figures and tables (`figures/`)** ([README](paper_results/README.md)) |
| `docker/`, `Dockerfile` | PostgreSQL 18.4 + IMDB container used in the experiments ([README](docker/README.md)) |
| `Redbench/` | Modified copy of the Redbench workload generator (Apache License 2.0; see [Third-party code and data](#third-party-code-and-data)) |
| `tests/`, `.github/workflows/` | Unit and regression tests; CI (tests, import check, regeneration of the figures) |
| `requirements.txt`, `pyproject.toml`, `uv.lock` | Python dependencies (versions of the experiments) |

Input query sets in `01_queries/`:

| Query set | Content | Used by |
|---|---|---|
| `job-ceb-2/` | 2,515 JOB and CEB queries and their frequencies: `frequency_time_dependent_24_2_10.json` (Cycles), `_24_mono.json` (Evolution and Stagnation), `_24_peak.json` (Growth and Spikes), `_{12,18,24,30,36,42}_mono.json` (time-step scaling) | RQ1, RQ3, RQ4 |
| `Redbench_synthetic/` | 2,284 queries and `frequency_time_dependent_2h_x2_50x.json`, generated with Redbench from anonymized cloud traces | RQ1, RQ2 |
| `job-ceb-2-q{20000,...,100000}/` | Frequencies of the synthetic query sets obtained by block-replicating job-ceb-2; their plans and costs are generated by `paper_scripts/rq3_exp3_3_query_scaling.sh` | RQ3 Exp3-3 |
| `job/` | The 113 JOB queries (not used by the experiments of the paper) | — |

### Generated by running the experiments

These directories are created by the steps above and are not in the repository (`.gitignore`).

| Path | Created by | Content |
|---|---|---|
| `.venv/` | Step 1 | Python environment |
| `02_json/<set>/` | Preprocessing (Phases 1, 3) | EXPLAIN plans of the queries, with node IDs |
| `03_parsed/<set>/` | Preprocessing (Phase 2); `rq3_exp3_3_query_scaling.sh` | Parsed plans and MV candidates (`qp_class.pkl`, up to 13 GB), `parse_summary.json`; `sparse_base.pkl` and `job-ceb-2-q*/` for the query-scaling experiment |
| `04_migration/<set>/` | Preprocessing (Phases 4–5.5); `rq3_exp3_3_query_scaling.sh` | Migration plans and costs (`simple_migration_plans.json`, `simple_migration_costs.json` and the settings used in `simple_migration_costs.meta.json`) |
| `time_dependent_output/<set>/` | `scripts/run_experiment_normal.py` (Phases 6–9) | Working directory of the driver: the latest optimization and benchmark results, MV SQL per time step (`timestep_*.sql`) and rewritten queries (`jobs/`) |
| `time_dependent_output/rq*/` | `paper_scripts/*.sh` | Results of the paper experiments, in the same layout as `paper_results/rq*/`, with logs in `log/` |
| `time_dependent_output/prep/log/` | `paper_scripts/00_prepare.sh` | Logs of the preprocessing |
| `paper_figures/output/` | `paper_figures/make_all.sh` | Figures and tables |

Every result JSON written by the driver records the settings of its run (command line, options, code version and the
preprocessing settings) under the key `run_config`. With `FORCE_PREP=1`, the preprocessing moves
existing outputs to `<dir>/<set>__backup_<timestamp>/` instead of deleting them; the experiment
scripts keep intermediate files of earlier runs in `time_dependent_output/<set>/_stash/`
(see [paper_scripts/README.md](paper_scripts/README.md)).

## Reference: experiment pipeline

`scripts/run_experiment_normal.py` runs the pipeline phase by phase.
The scripts in `paper_scripts/` call it with the settings of the paper.

| Phase | Content | Output |
|---|---|---|
| 1 | EXPLAIN plans of all queries (needs the DB) | `02_json/<set>/*.json` |
| 2 | Plan parsing, MV candidate enumeration, utilities | `03_parsed/<set>/qp_class.pkl` |
| 3 | Node IDs added to the plans | `02_json/<set>/*.json` |
| 4 | Migration plan enumeration | `04_migration/<set>/simple_migration_plans.json` |
| 5 | Migration cost estimation by sampling (needs the DB) | `04_migration/<set>/simple_migration_costs.json` |
| 5.5 | Cost recalculation with the node structure of the parsed plans (`--phase 5.5`, or `scripts/recalculate_costs.py --overwrite`) | same file, overwritten |
| 6 | Optimization (`--optimization-mode dynamic` = proposed, `static`, `adaptive`) | `time_dependent_output/<set>/*_optimization_result<suffix>.json` |
| 7 | MV creation/deletion SQL per time step | `time_dependent_output/<set>/timestep_*.sql` |
| 8 | Query rewriting to use the MVs | `time_dependent_output/<set>/jobs/` |
| 9 | Benchmark (needs the DB) | `time_dependent_output/<set>/benchmark_results_<mode><suffix>.json` |

`--phase all` runs Phases 1–9 including the cost recalculation (5.5); `--phase post-opt` runs Phases 6–9.
Use `--recalc` so that the optimization uses the recalculated costs (as in the paper). Main options:

| Option | Meaning |
|---|---|
| `--query-set <name>` | Query set in `01_queries/` |
| `--exp-suffix <suffix>` | Frequency file `frequency_time_dependent<suffix>.json`; also appended to the result file names |
| `--optimization-mode {dynamic,static,adaptive}` | Proposed (time-dependent ILP), Static, Adapt |
| `--use-pruning [--pruning-parallel] [--pruning-workers N]` | MV candidate pruning with the workload summary tree |
| `--static-timestep average --static-algorithm utility` | Static baseline (average frequencies over all time steps) |
| `--window-size 4 --freq-weight linear` | Adapt baseline |
| `--b-max <MB>` | Storage constraint |
| `--recalc` | Use the recalculated costs (always used in the paper) |
| `--ease` | Execute each query once per time step and multiply by its frequency |
| `--noise-ratio <r>` / `--benchmark-mode <mode>` | Benchmark with prediction errors (Phase 9) |
| `--use-docker` | Access PostgreSQL through the `mv_postgres` container |

## Troubleshooting

- **`GurobiError: No Gurobi license found`**: set `GRB_LICENSE_FILE` to the path of the license file.
- **PostgreSQL is not reachable**: check `docker exec mv_postgres pg_isready -U postgres` and
  `docker logs mv_postgres`. `bash docker/verify_env.sh` checks the whole environment.
- **`qp_class.pkl` not found**: run the preprocessing (`bash paper_scripts/00_prepare.sh`).
- **A script stops with "A file with the same name is already stashed"**: a previous run was
  interrupted; see "Staging and existing files" in [paper_scripts/README.md](paper_scripts/README.md).

## Third-party code and data

| Item | Where it is used | Source | License / terms |
|---|---|---|---|
| Redbench | `Redbench/` (modified copy; the changes are listed at the top of [Redbench/README.md](Redbench/README.md)) | [DataManagementLab/Redbench](https://github.com/DataManagementLab/Redbench), commit `a129890` (2025-11-19); J. Wehrstein, R. Heinrich, M. Stoian, et al. *Redbench: Workload Synthesis From Cloud Traces*. [arXiv:2511.13059](https://arxiv.org/abs/2511.13059), 2025 | Apache License 2.0 |
| Redset | Query arrival times behind `01_queries/Redbench_synthetic/` (through Redbench; the dataset itself is not included) | [amazon-science/redset](https://github.com/amazon-science/redset); A. van Renen, D. Horn, P. Pfeil, et al. *Why TPC Is Not Enough: An Analysis of the Amazon Redshift Fleet*. PVLDB 17(11):3694–3706, 2024 | CC BY-NC 4.0 |
| Join Order Benchmark (JOB) | Queries in `01_queries/` | V. Leis, A. Gubichev, A. Mirchev, et al. *How Good Are Query Optimizers, Really?* PVLDB 9(3):204–215, 2015 (queries also distributed at [gregrahn/join-order-benchmark](https://github.com/gregrahn/join-order-benchmark)) | — |
| Cardinality Estimation Benchmark (CEB) | Queries in `01_queries/` | [learnedsystems/CEB](https://github.com/learnedsystems/CEB); P. Negi, R. Marcus, A. Kipf, et al. *Flow-Loss: Learning Cardinality Estimates That Matter*. PVLDB 14(11):2019–2032, 2021 | MIT (repository) |
| IMDB data (JOB version, CSV files of May 2013) | Loaded into the PostgreSQL container by the `Dockerfile` (downloaded during the build; not included) | https://event.cwi.nl/da/job/imdb.tgz | IMDb terms of use ([imdb.com/interfaces](https://www.imdb.com/interfaces/)) |
