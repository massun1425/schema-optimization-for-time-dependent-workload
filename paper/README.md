# Experiment scripts for the paper

Shell scripts that produce the results reported in the paper
("Schema Optimization for Time-Dependent Workloads", EDBT 2026).
The experiment driver itself is `scripts/run_experiment_normal.py`.
All results are collected under `time_dependent_output/rq*/`; existing results
(e.g. the `*_ok` directories) are never modified.

## Scripts

| Script | Paper | Content | Output |
|---|---|---|---|
| `00_prepare.sh` | — | Phases 1–5 + cost recalculation (job-ceb-2, Redbench_synthetic) | `02_json/`, `03_parsed/`, `04_migration/` (skipped if present) |
| `rq1_exp1_1_timestep_time.sh` | Fig. 7 | Execution time per time step (3 patterns + Redbench, 3 methods) | `time_dependent_output/rq1/exp1_1/{job-ceb-2,Redbench_synthetic}/` |
| `rq1_exp1_2_timestep_scaling.sh` | Fig. 8 | Optimization time vs. number of time steps (T = 12–42, with/without pruning) | `time_dependent_output/rq1/exp1_2/` |
| `rq1_exp1_3_query_scaling.sh` | Fig. 9 | Optimization time vs. number of queries (20k–100k; Static / with / without pruning) | `time_dependent_output/rq1/exp1_3/job-ceb-2-q{N}/` |
| `rq2_prediction_recall.sh` | Fig. 10 | Robustness against prediction recall (= 100 − noise) | `time_dependent_output/rq2/` |
| `rq3_pruning.sh` | Table 2 | With vs. without candidate pruning | `time_dependent_output/rq3/` |
| `rq4_capacity.sh` | Fig. 11 | Storage constraint 500–2000 MB | `time_dependent_output/rq4/{24_2_10,24_mono,24_peak}/b{500..2000}/` |
| `run_all.sh` | — | Runs all of the above in dependency order | |
| `../paper_results/collect_paper_results.sh` | — | Copies the original results reported in the paper into `paper_results/` (same layout as `rq*/`; copies only, never overwrites). Located in `paper_results/` | `paper_results/` |
| `common.sh` | — | Shared settings and helpers (sourced only) | |

Each output directory contains the result JSONs and `log/` (execution logs).

## Experimental settings (checked against the result JSONs of the paper)

- Common: `--recalc`, B_max = 500 MB (except RQ4), T = 24, benchmarks use `--ease`
  (each query is executed once and its time is multiplied by its frequency).
- Frequency files: `_24_2_10` / `_24_mono` / `_24_peak` for job-ceb-2 (**not** the `_rand` variants),
  `_2h_x2_50x` for Redbench.
- Proposed: `--optimization-mode dynamic --use-pruning`
  - Sequential pruning for RQ1 Exp1-1, RQ3 and RQ4 b500.
  - `--pruning-parallel` for RQ1 Exp1-2 and RQ4 b1000 and above;
    `--pruning-parallel --pruning-workers 16` for RQ1 Exp1-3.
  - (As in the original runs. The promising MV set is identical for sequential and
    parallel pruning, but the pruning time differs.)
- Static: `--optimization-mode static --static-timestep average --static-algorithm utility`
- Adapt: `--optimization-mode adaptive --window-size 4 --freq-weight linear`
- Without pruning: each run is stopped after 24 h. A run that exceeds it is marked as
  DNF and larger problem sizes are not run.

## Reuse of results (same as in the paper data)

Runs with identical settings are executed only once and copied (`REUSE=1` by default):

- RQ2 recall 100% ← Redbench results of RQ1 Exp1-1
- RQ3 with pruning ← Proposed of RQ1 Exp1-1
- RQ4 b500 ← all three methods of RQ1 Exp1-1

This is why `run_all.sh` runs Exp1-1 first.
The noise experiments of RQ2 do not repeat the optimization: Phases 7/8 are regenerated
from the recall-100% optimization result and only Phase 9 is run.

## Staging and existing files

`run_experiment_normal.py` writes its results with fixed names directly under
`time_dependent_output/<query_set>/` (staging). Staging also contains existing results
(e.g. the Fig. 9 source data in `job-ceb-2-q{N}/`), so the scripts work as follows:

1. **Result JSONs**: right before a run, only the existing files whose names collide
   with the files about to be written are moved to `<set>/_stash/in_use/`. They are put
   back after the results have been moved to `rq*/`, and also on errors or interruption
   (EXIT trap; only if the original location is free).
   → **Existing results stay at their original paths after the run.**
2. **Intermediates** (`timestep_*.sql`, `static_*initial_mvs.sql`, `jobs/`): Phases 7/8
   delete and regenerate them, so the post-opt scripts move them once to
   `<set>/_stash/intermediates_<timestamp>/` on their first run (marker: `.paper_staging`).
   The current ones belong to the last run and do not correspond to the paper results,
   but they are kept just in case.
3. After every run, the results are moved to `rq*/` (runs without pruning get `_wo`,
   runs with pruning in the scaling experiments get `_wp`).
4. Runs whose results already exist in the output directory are skipped, so an
   interrupted run can be resumed by running the script again.

If files remain in `_stash/in_use/` after an interruption, the original location
contains partial output of the interrupted run. Check it manually and clean up
(in that case the next run stops for safety).

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `DRY_RUN` | 0 | 1: print the commands without running anything (no file operations) |
| `FORCE` | 0 | 1: re-run / re-copy even if results exist |
| `REUSE` | 1 | 0: do not reuse RQ1 results; run in each RQ |
| `PY` | `.venv/bin/python` | Python 3.12 environment |
| `CONTAINER` | `mv_postgres` | PostgreSQL container name (restarted before each benchmark) |
| `TIMEOUT` | `24h` | Time limit for optimization without pruning |
| `SUFFIXES` / `CAPS` / `TIMESTEPS` / `QUERY_COUNTS` / `NOISE_PCTS` / `SETS` | paper values | Override to run a subset (e.g. `SUFFIXES="_24_mono"`) |
| `SKIP_REDBENCH` | 0 | Skip Redbench in Exp1-1 |
| `FORCE_PREP` | 0 | 1: regenerate the preprocessing outputs (existing ones are moved to `<dir>/<set>__backup_<timestamp>`) |

## Usage

```bash
# Check the commands that would be executed (runs and changes nothing)
DRY_RUN=1 bash paper/run_all.sh

# All experiments
nohup bash paper/run_all.sh > paper_run_all.log 2>&1 &

# Individual experiments
bash paper/rq3_pruning.sh
SUFFIXES="_24_peak" CAPS="1000" bash paper/rq4_capacity.sh
```

## Prerequisites and notes

- The PostgreSQL container (`mv_postgres`) must be running. Experiments that only run
  Phase 6 (Exp1-2, Exp1-3) do not need the DB.
- To create the container use `bash docker/create_container.sh`; to check it use
  `bash docker/verify_env.sh` (see `docker/README.md`).
- A Gurobi license is required (see the root `README.md`).
- Settings not recorded in the result JSONs, taken from the original shell scripts:
  - `--freq-weight linear` for Adapt
  - the sampling rate of the preprocessing (job-ceb-2 = high, Redbench = low)
- Figures and tables are generated from `rq*/` by `paper_figures/`.
