# Results reported in the paper

This directory contains the result files behind every figure and table of the paper
("Schema Optimization for Time-Dependent Workloads", EDBT). It has the same layout as the
output of the experiment scripts in `paper/` (`time_dependent_output/rq*/`), so the figures
and tables can be regenerated without re-running the experiments:

```bash
bash paper_figures/make_all.sh --td-dir paper_results
```

The files were collected from the original experiment runs by `collect_paper_results.sh` in this
directory (copies only). `SHA256SUMS` lists the checksums of all result files (everything except
`README.md`, `SHA256SUMS`, the script and `figures/`); `sha256sum -c SHA256SUMS` inside this
directory verifies them. Re-running the experiments writes to `time_dependent_output/`
and never touches this directory.

## Contents

| Directory | Paper | Content |
|---|---|---|
| `rq1/exp1_1/job-ceb-2/` | Fig. 7 | Cycles (`_24_2_10`), Evolution and Stagnation (`_24_mono`), Growth and Spikes (`_24_peak`); Proposed / Static / Adapt |
| `rq1/exp1_1/Redbench_synthetic/` | Fig. 7 | Redbench synthetic (`_2h_x2_50x`); Proposed / Static / Adapt |
| `rq1/exp1_2/` | Fig. 8 | Optimization with (`_wp`) and without (`_wo`) pruning for T = 12, 18, 24, 30, 36, 42 (`_{T}_mono`) |
| `rq1/exp1_3/job-ceb-2-q{N}/` | Fig. 9 | Optimization for N = 20k–100k queries: Static, with pruning (`_wp`), without pruning (`_wo`) |
| `rq2/` | Fig. 10 | Redbench synthetic with prediction noise 5–50% (`_noise{P}`; recall = 100 − P) and without noise |
| `rq3/` | Table 2 | With pruning and without pruning (`_wo`) for the three patterns |
| `rq4/{24_2_10,24_mono,24_peak}/b{500,1000,1500,2000}/` | Fig. 11 | Storage constraint B_max = 500–2000 MB; Proposed / Static / Adapt |
| `figures/` | Figs. 5–11, Table 2 | The figures (PDF) and Table 2 (LaTeX, Markdown) of the paper, generated from this directory with `bash paper_figures/make_all.sh --td-dir paper_results --out-dir paper_results/figures` |

### File types

| File | Content |
|---|---|
| `benchmark_results_{dynamic,static,adaptive_w4}<suffix>.json` | Benchmark of Proposed / Static / Adapt: `timestep_results[t]` (migration and query execution per time step) and `summary.total_benchmark_time` |
| `td_mv_optimization_result<suffix>.json` | Optimization result of Proposed: selected MVs per time step (`migration_analysis`), objective value, solve / pruning / phase times, pruning statistics (`pruning_info`) |
| `static_mv_optimization_result<suffix>.json` | Optimization result of Static (selected MVs, `execution_time`) |
| `adaptive_mv_optimization_result_w4<suffix>.json` | Optimization result of Adapt (window size 4) |
| `DNF_24_mono_wo.txt` | Marker: the optimization without pruning did not finish within 24 hours (or was skipped because a smaller size had timed out) |

## Notes

- **Settings.** B_max = 500 MB (except RQ4), 24 time steps (except RQ1 Exp1-2), `--recalc`,
  benchmarks with `--ease`. See `paper/README.md` for the exact options of every method.
- **Total execution time** (`summary.total_benchmark_time`) is the sum of query execution and
  migration over all time steps. For Static it includes the one-time initial MV build, which
  Fig. 7 adds to the first time step.
- **Shared runs.** Runs with identical settings are shared, as in the original experiments:
  `rq2/` without noise = `rq1/exp1_1/Redbench_synthetic/`, the with-pruning files of `rq3/` =
  Proposed in `rq1/exp1_1/job-ceb-2/`, and `rq4/*/b500/` = `rq1/exp1_1/job-ceb-2/`.
- **Fig. 9 without pruning.** N = 60k timed out after 24 hours; N = 80k and 100k were therefore
  not run. All three are reported as DNF.
- **Times.** Execution and optimization times were measured on the machine described in the
  paper; they will differ on other hardware.
