# Schema Optimization for Time-Dependent Workloads — Experiments

This repository contains the implementation and the experiment scripts of the paper
**"Schema Optimization for Time-Dependent Workloads"** (EDBT 2027).
The method selects a time series of materialized views (MVs) with an integer linear program
that maximizes the total utility of the MVs minus the migration cost between time steps, and
prunes MV candidates with a *workload summary tree*.

This README explains how to reproduce all experiments of the paper, from setting up the
environment to generating the figures and tables.

## Results and figures of the paper

**[`paper_results/`](paper_results/README.md) contains the results reported in the paper and
its figures and tables:**

- `paper_results/rq1/` … `paper_results/rq4/`: the result files (JSON) behind every figure and
  table, organized by research question (RQ1: Figs. 7–9, RQ2: Fig. 10, RQ3: Table 2, RQ4: Fig. 11).
- `paper_results/figures/`: the figures (PDF) of the paper (Figs. 5–11) and Table 2 (LaTeX and
  Markdown), generated from these files.

The figures and tables can be regenerated from the included results without running any
experiment (no database or Gurobi license needed):

```bash
bash paper_figures/make_all.sh --td-dir paper_results --out-dir paper_results/figures
```

To reproduce the results themselves, follow the steps below.

## Contents

| Path | Content |
|---|---|
| `scripts/run_experiment_normal.py` | Experiment driver (Phases 1–9, see [Reference](#reference-experiment-pipeline)) |
| `core/`, `src/`, `migration/`, `mv_generation/`, `benchmark/`, `config/`, `utils/` | Implementation (optimizer, candidate pruning, cost estimation, query rewriting, benchmark) |
| `paper/` | Shell scripts that run every experiment of the paper ([paper/README.md](paper/README.md)) |
| `paper_figures/` | Scripts that turn the results into the figures and tables of the paper ([paper_figures/README.md](paper_figures/README.md)) |
| `paper_results/` | **The results reported in the paper (`rq*/`) and its figures and tables (`figures/`)** ([paper_results/README.md](paper_results/README.md)) |
| `docker/`, `Dockerfile` | PostgreSQL 18.4 + IMDB container used in the experiments ([docker/README.md](docker/README.md)) |
| `01_queries/` | Query sets and time-dependent query frequencies |
| `02_json/`, `03_parsed/`, `04_migration/` | Preprocessing outputs (EXPLAIN plans, parsed plans, migration plans and costs) || `time_dependent_output/` | Experiment results (`rq*/` for the paper experiments) |
| `Redbench/` | Redbench workload generator (used to build the Redbench synthetic workload) |

## 1. Requirements

- **Hardware.** The paper used an HPE ProLiant DL385 Gen10 Plus with two AMD EPYC 7542
  (32 cores each) and 2 TB of memory. The PostgreSQL container is limited to 8 cores and 16 GB.
  The optimizer runs outside the container; the largest query-scaling experiment (100k queries)
  loads a 13 GB parse result.
- **Software.** Linux, Docker, Python 3.12, Gurobi 12.0 (an academic license is sufficient).
- **Disk.** About 5 GB for the container image, about 6 GB for the preprocessing outputs of the two
  query sets, and about 36 GB for the synthetic query sets of the query-scaling experiment.

## 2. Setup

### 2.1 Python environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` pins the package versions used for the experiments of the paper
(Gurobi 12.0.1, NumPy, psycopg2, PyYAML, sqlparse, Matplotlib for the figures, and
FastAPI/Uvicorn for the dashboard). With [uv](https://docs.astral.sh/uv/), `uv sync`
installs the same versions from `uv.lock` (`uv sync --extra dev` adds pytest and the linters).

### 2.2 Gurobi license

Obtain a license from [gurobi.com](https://www.gurobi.com/) and make it visible to `gurobipy`:

```bash
export GRB_LICENSE_FILE=/path/to/gurobi.lic
```

### 2.3 PostgreSQL container

```bash
bash docker/create_container.sh     # build -> start -> load IMDB (tens of minutes) -> verify
bash docker/verify_env.sh           # check that the container matches the paper environment
```

The container is named `mv_postgres` and listens on port 5432 (both are assumed by the code).
It runs PostgreSQL 18.4 with the server parameters of the paper (shared_buffers = 2 GB,
work_mem = 128 MB, jit = off, ...), limited to 8 cores, 16 GB of memory and 4 GB of shared memory.
The build downloads the IMDB data of the Join Order Benchmark (about 1.2 GB).
See [docker/README.md](docker/README.md) for details.

## 3. Input data

| Query set | Content | Used by |
|---|---|---|
| `01_queries/job-ceb-2/` | 2,515 JOB and CEB queries and their frequencies: `frequency_time_dependent_24_2_10.json` (Cycles), `_24_mono.json` (Evolution and Stagnation), `_24_peak.json` (Growth and Spikes), `_{12,18,24,30,36,42}_mono.json` (time-step scaling) | RQ1, RQ3, RQ4 |
| `01_queries/Redbench_synthetic/` | 2,284 queries and `frequency_time_dependent_2h_x2_50x.json`, generated with Redbench from anonymized cloud traces | RQ1, RQ2 |
| `01_queries/job-ceb-2-q{20000,...,100000}/` | Synthetic query sets obtained by block-replicating job-ceb-2 (generated automatically by `paper/rq1_exp1_3_query_scaling.sh` if missing) | RQ1 (query scaling) |

## 4. Reproducing the experiments

All commands are run from the repository root.

### 4.1 Preprocessing

```bash
bash paper/00_prepare.sh
```

For each query set this runs EXPLAIN (Phase 1), plan parsing and MV candidate enumeration
(Phases 2–3), migration plan enumeration (Phase 4), sampling-based cost estimation (Phase 5),
and the cost recalculation. Query sets whose outputs already exist are skipped.

### 4.2 Experiments

| RQ | Script | Paper | Output (`time_dependent_output/`) | Approx. run time |
|---|---|---|---|---|
| RQ1 | `paper/rq1_exp1_1_timestep_time.sh` | Fig. 7 | `rq1/exp1_1/` | ~4.5 days |
| RQ1 | `paper/rq1_exp1_2_timestep_scaling.sh` | Fig. 8 | `rq1/exp1_2/` | ~5 hours |
| RQ1 | `paper/rq1_exp1_3_query_scaling.sh` | Fig. 9 | `rq1/exp1_3/` | ~3 days |
| RQ2 | `paper/rq2_prediction_recall.sh` | Fig. 10 | `rq2/` | ~2 days |
| RQ3 | `paper/rq3_pruning.sh` | Table 2 | `rq3/` | ~1.5 days |
| RQ4 | `paper/rq4_capacity.sh` | Fig. 11 | `rq4/` | ~12 days |

Run all of them in dependency order with:

```bash
DRY_RUN=1 bash paper/run_all.sh                          # print the commands only
nohup bash paper/run_all.sh > paper_run_all.log 2>&1 &   # run everything
```

- Run times are estimates from the original runs (about 11 hours per benchmark run on
  job-ceb-2 and 2–3 hours on Redbench). The optimization without pruning in the scalability
  experiments is stopped after 24 hours and reported as DNF, as in the paper.
- RQ2, RQ3 and RQ4 reuse the results of RQ1 Exp1-1 that have identical settings, so
  `run_all.sh` runs it first.
- Runs whose results exist are skipped; re-running a script resumes it.
- Subsets can be run with environment variables, e.g.
  `SUFFIXES="_24_mono" CAPS="1000" bash paper/rq4_capacity.sh`.

The exact settings of every experiment (methods, flags, storage constraints, output layout)
are documented in [paper/README.md](paper/README.md).

### 4.3 Figures and tables

```bash
bash paper_figures/make_all.sh                            # from your own runs (time_dependent_output/rq*/)
bash paper_figures/make_all.sh --td-dir paper_results     # from the results reported in the paper
```

The second command regenerates the figures and tables of the paper from the included result
files in `paper_results/` without running any experiment (no database or Gurobi license needed).
Both write the figures (PDF) and Table 2 (LaTeX and Markdown) to `paper_figures/output/`:

| Paper | Output |
|---|---|
| Fig. 5 | `setup_frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf` |
| Fig. 6 | `setup_redbench_total_count.pdf` |
| Fig. 7 | `rq1_exp1_1_timestep_time_{cycles,evolution_and_stagnation,growth_and_spikes,redbench_synthetic}.pdf` |
| Fig. 8 | `rq1_exp1_2_timestep_scaling.pdf` |
| Fig. 9 | `rq1_exp1_3_query_scaling.pdf` |
| Fig. 10 | `rq2_prediction_recall.pdf` |
| Table 2 | `rq3_pruning.tex`, `rq3_pruning.md` |
| Fig. 11 | `rq4_capacity.pdf` |

Execution times measured on a different machine will differ from the paper. The MVs selected by
the optimizer (promising candidates, objective value and schedule) are deterministic for a given
input and Gurobi configuration.

## Reference: experiment pipeline

`scripts/run_experiment_normal.py` runs the pipeline phase by phase.
The scripts in `paper/` call it with the settings of the paper.

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
- **`qp_class.pkl` not found**: run the preprocessing (`bash paper/00_prepare.sh`).
- **A script stops with "A file with the same name is already stashed"**: a previous run was
  interrupted; see "Staging and existing files" in [paper/README.md](paper/README.md).

## Appendix: generating a new workload with Redbench

This is not needed to reproduce the paper. The scripts that convert Redbench workloads into
query sets and combine them are in [scripts/redbench_synthesizer/](scripts/redbench_synthesizer/README.md). To build a new
time-dependent workload, generate `workload.csv` with Redbench (see
[Redbench/README.md](Redbench/README.md)) and convert it:

```bash
python scripts/redbench_synthesizer/generate_queryset_from_workload_csv.py \
  --csv-path <workload.csv> --queries-json-path <queries.json> \
  --output-query-dir 01_queries/<query_set> \
  --start <start time, e.g. 2024-05-25T00:00:00> \
  --end <end time, e.g. 2024-05-26T23:59:59> \
  --step-hours <hours per time step, e.g. 2> \
  --freq-suffix <suffix, e.g. _2h> \
  --sanitize-ceb
```

The resulting `01_queries/<query_set>/` can then be processed from Phase 1.
