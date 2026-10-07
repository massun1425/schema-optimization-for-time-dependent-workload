# Figure and table scripts for the paper

Generates exactly the figures and tables of the paper from the results of `paper_scripts/*.sh`
(`time_dependent_output/rq*/`). The plotting code is ported from the scripts that produced
the figures in the paper; only the input paths and the output location were changed.
Script and output names follow the RQ/experiment numbering of `paper_scripts/`
(`setup_` = figures of the experimental setup).

## Figures, tables, inputs and outputs

All outputs are written to `paper_figures/output/` (change with `--out-dir`).
The `rq*/` inputs are under `time_dependent_output/`.

| Script | Experiment | Output | Input |
|---|---|---|---|
| `setup_frequency_patterns.py` | Workload setup | `setup_frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf` | `01_queries/job-ceb-2/frequency_time_dependent_{24_2_10,24_mono,24_peak}.json` |
| `setup_redbench_total_count.py` | Workload setup | `setup_redbench_total_count.pdf` | `01_queries/Redbench_synthetic/frequency_time_dependent_2h_x2_50x.json` |
| `rq1_exp1_1_timestep_time.py` | RQ1 Exp1-1 | `rq1_exp1_1_timestep_time_{cycles,evolution_and_stagnation,growth_and_spikes,redbench_synthetic}.pdf` | `rq1/exp1_1/` |
| `rq2_prediction_recall.py` | RQ2 | `rq2_prediction_recall.pdf` | `rq2/` |
| `rq3_exp3_1_pruning.py` | RQ3 Exp3-1 | `rq3_exp3_1_pruning.tex`, `rq3_exp3_1_pruning.md` | `rq3/exp3_1/` |
| `rq3_exp3_2_timestep_scaling.py` | RQ3 Exp3-2 | `rq3_exp3_2_timestep_scaling.pdf` | `rq3/exp3_2/` |
| `rq3_exp3_3_query_scaling.py` | RQ3 Exp3-3 | `rq3_exp3_3_query_scaling.pdf` | `rq3/exp3_3/` |
| `rq4_capacity.py` | RQ4 | `rq4_capacity.pdf` | `rq4/` |

The docstring of each script lists the files and fields it uses.

## Usage

```bash
bash paper_figures/make_all.sh                                # generate everything
bash paper_figures/make_all.sh --td-dir paper_results         # from the results reported in the paper
.venv/bin/python paper_figures/rq1_exp1_1_timestep_time.py    # generate a single figure

# Change the input/output directories (arguments shared by all scripts)
bash paper_figures/make_all.sh --td-dir <directory containing rq*> --out-dir <output directory>
```

If inputs are missing, the script lists the missing files and exits with an error.
For RQ3 Exp3-3 without pruning, either the result JSON or `DNF_24_mono_wo.txt`
(written by `paper_scripts/rq3_exp3_3_query_scaling.sh`) is required.

The PDFs contain no creation date, so the same input always yields the same PDF.
