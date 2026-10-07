# Experiment scripts for the paper

Shell scripts that produce the results reported in the paper
("Schema Optimization for Time-Dependent Workloads").
The experiment driver itself is `scripts/run_experiment_normal.py`.
All results are collected under `time_dependent_output/rq*/`; existing results
(e.g. the `*_ok` directories) are never modified.

## Scripts

| Script | Experiment | Content | Output |
|---|---|---|---|
| `00_prepare.sh` | — | Phases 1–5 + cost recalculation (job-ceb-2, Redbench_synthetic) | `02_json/`, `03_parsed/`, `04_migration/` (skipped if present) |
| `rq1_exp1_1_timestep_time.sh` | RQ1 Exp1-1 | Execution time per time step (3 patterns + Redbench, 3 methods) | `time_dependent_output/rq1/exp1_1/{job-ceb-2,Redbench_synthetic}/` |
| `rq2_prediction_recall.sh` | RQ2 | Robustness against prediction recall (= 100 − noise) | `time_dependent_output/rq2/` |
| `rq3_exp3_1_pruning.sh` | RQ3 Exp3-1 | With vs. without candidate pruning | `time_dependent_output/rq3/exp3_1/` |
| `rq3_exp3_2_timestep_scaling.sh` | RQ3 Exp3-2 | Optimization time vs. number of time steps (T = 12–42, with/without pruning) | `time_dependent_output/rq3/exp3_2/` |
| `rq3_exp3_3_query_scaling.sh` | RQ3 Exp3-3 | Optimization time vs. number of queries (20k–100k; Static / with / without pruning) | `time_dependent_output/rq3/exp3_3/job-ceb-2-q{N}/` |
| `rq4_capacity.sh` | RQ4 | Storage constraint 500–2000 MB | `time_dependent_output/rq4/{24_2_10,24_mono,24_peak}/b{500..2000}/` |
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
  - Sequential pruning for RQ1 Exp1-1 and RQ4 b500.
  - `--pruning-parallel` for RQ3 Exp3-1 (optimization), RQ3 Exp3-2 and RQ4 b1000 and above;
    `--pruning-parallel --pruning-workers 16` for RQ3 Exp3-3.
  - (The promising MV set and the selected MVs are identical for sequential and parallel
    pruning; only the pruning time differs.)
- Static: `--optimization-mode static --static-timestep average --static-algorithm utility`
- Adapt: `--optimization-mode adaptive --window-size 4 --freq-weight linear`
- Without pruning: each run is stopped after 24 h. A run that exceeds it is marked as
  DNF and larger problem sizes are not run.

## Reuse of results (same as in the paper data)

Runs with identical settings are executed only once and copied to the other experiments

## Staging and existing files

`run_experiment_normal.py` writes its results with fixed names directly under
`time_dependent_output/<query_set>/` (staging). Staging also contains existing results
(e.g. the Exp3-3 source data in `job-ceb-2-q{N}/`), so the scripts work as follows:

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
DRY_RUN=1 bash paper_scripts/run_all.sh

# All experiments
nohup bash paper_scripts/run_all.sh > paper_run_all.log 2>&1 &

# Individual experiments
bash paper_scripts/rq3_exp3_1_pruning.sh
SUFFIXES="_24_peak" CAPS="1000" bash paper_scripts/rq4_capacity.sh
```

## Prerequisites and notes

- The PostgreSQL container (`mv_postgres`) must be running. Experiments that only run
  Phase 6 (Exp3-2, Exp3-3) do not need the DB.
- To create the container use `bash docker/create_container.sh`; to check it use
  `bash docker/verify_env.sh` (see `docker/README.md`).
- A Gurobi license is required (see the root `README.md`).
- Settings not recorded in the result JSONs, taken from the original shell scripts:
  - `--freq-weight linear` for Adapt
  - the sampling rate of the preprocessing: the original runs used the high-rate sampler for
    job-ceb-2 and the low-rate sampler for Redbench. `00_prepare.sh` now uses the more accurate
    high-rate sampler for both query sets, so a new preprocessing run of Redbench_synthetic
    produces different costs than those behind the Redbench results in `paper_results/`.
- Figures and tables are generated from `rq*/` by `paper_figures/`.
