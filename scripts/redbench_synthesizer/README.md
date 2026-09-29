# Redbench synthesizer

Tools that convert workloads generated with [Redbench](../../Redbench/README.md) into query
sets (`01_queries/<query_set>/`) and combine them. They are not needed to reproduce the paper.

| File | Role |
|---|---|
| `generate_queryset_from_workload_csv.py` | Convert a Redbench `workload.csv` into SQL files and a frequency file (one time step per `--step-hours`) |
| `scale_frequency.py` | Multiply all frequencies of a frequency file by an integer factor |
| `merge_query_folders_sum.py` | Combine two query sets by summing the frequencies of the same time step |
| `merge_query_folders.py` | Combine two query sets by concatenating their time steps |
| `normalize_queryset_table_versions.py` | Map versioned table names (e.g. `movie_info_1`) back to the IMDB tables (Redbench generation strategy only) |
| `build_cluster_53_55_combined.sh` | Build the combined query set of clusters 53 and 55 (base of `Redbench_synthetic`) |
| `redbench_configs/` | Redbench configurations of the workloads used by `build_cluster_53_55_combined.sh` |

## Usage

```bash
# Workload -> query set
python scripts/redbench_synthesizer/generate_queryset_from_workload_csv.py \
  --csv-path <workload.csv> --queries-json-path <queries.json> \
  --output-query-dir 01_queries/<set> \
  --start 2024-05-25T00:00:00 --end 2024-05-26T23:59:59 \
  --step-hours 2 --freq-suffix _2h --sanitize-ceb

# Scale the frequencies
python scripts/redbench_synthesizer/scale_frequency.py \
  --input  01_queries/<set>/frequency_time_dependent_2h.json \
  --output 01_queries/<set>/frequency_time_dependent_2h_x2.json --factor 2

# Combine two query sets
python scripts/redbench_synthesizer/merge_query_folders_sum.py \
  --dir1 01_queries/<set1> --dir2 01_queries/<set2> --out 01_queries/<combined> \
  --freq-name frequency_time_dependent_2h_x2.json

# Clusters 53 + 55 in one step (existing outputs are not overwritten; OUT_ROOT changes the location)
OUT_ROOT=/tmp/rebuild bash scripts/redbench_synthesizer/build_cluster_53_55_combined.sh
```

Each Python script shows all options with `--help`. The resulting query set can be processed
from Phase 1 of `scripts/run_experiment_normal.py`.
