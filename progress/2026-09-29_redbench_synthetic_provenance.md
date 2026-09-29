# How Redbench_synthetic was built (2026-09-29)

Record of how `01_queries/Redbench_synthetic/` was built with the scripts in
[scripts/redbench_synthesizer/](../scripts/redbench_synthesizer/README.md), which turn
workloads generated with [Redbench](../Redbench/README.md) into query sets
(`01_queries/<query_set>/`) and combine them. **They are not needed to reproduce the paper**:
the query set is in the repository, and the experiments start from it.

| File | Purpose |
|---|---|
| `generate_queryset_from_workload_csv.py` | Redbench `workload.csv` → SQL files + frequency file (one time step per `--step-hours` bin) |
| `scale_frequency.py` | Multiply all frequencies by an integer factor (`_2h` → `_2h_x2`, → `_10x`, → `_50x`) |
| `merge_query_folders_sum.py` | Combine two query sets by summing the frequencies of the same time step |
| `merge_query_folders.py` | Combine two query sets by concatenating their time steps (not used for Redbench_synthetic) |
| `normalize_queryset_table_versions.py` | Map versioned table names (`movie_info_1`) back to IMDB tables; only needed for the Redbench *generation* strategy |
| `build_cluster_53_55_combined.sh` | Steps 2–4 below in one command |
| `redbench_configs/` | Redbench configurations (`used_config.json`) of the two source workloads |

## How Redbench_synthetic was built

`Redbench_synthetic` has 2,284 queries and 24 time steps of 2 hours. It combines the
workloads of Redset serverless clusters 53 and 55, which were matched to JOB/CEB queries by
Redbench, plus JOB/CEB queries added afterwards.

### 1. Redbench matching (Redbench)

Workloads were generated with the matching strategy (`matching_method: join`,
`only_select: true`) for several time windows of each cluster. The windows with the most
queries were chosen:

| Cluster | Redbench output (`Redbench/output/generated_workloads/imdb/serverless/`) | Window | Rows → unique queries | Config |
|---|---|---|---|---|
| 53 (database 1) | `cluster_53/database_1/050312-050511/` | 2024-05-03 12:00 – 05-05 11:59:59 | 629 → 427 | `redbench_configs/cluster_53_database_1_050312-050511.json` |
| 55 (database 0) | `cluster_55/database_0/0525-0526/` | 2024-05-25 00:00 – 05-26 23:59:59 | 23,442 → 628 | `redbench_configs/cluster_55_database_0_0525-0526.json` |

The output directories (`matching_<hash>/` by default) were renamed after the window. The
Redbench outputs are not in the repository (`Redbench/output/` is ignored); SHA-256 of the
files that were used:

```
201a939cd9c6c0bd032e4e44b99410b2bb408c3c55bfb06081cfd0d05ca0cd16  cluster_53/database_1/050312-050511/workload.csv
5c4d48c37b027a8b28b5f287936c64fbeb5481d91078d93ca36ab805f23af9d2  cluster_53/database_1/050312-050511/queries.json
04cfc268db0d8da92bdc9b6b6084b233036fee8d7ebb9ae1012b8f26dcd741b9  cluster_55/database_0/0525-0526/workload.csv
1850a518ccb9354e7e69e7b24f0817d639d4484e01d2f9a33a904afc2bc49059  cluster_55/database_0/0525-0526/queries.json
```

### 2–4. Query sets of each cluster and their combination (`build_cluster_53_55_combined.sh`)

```bash
bash scripts/redbench_synthesizer/build_cluster_53_55_combined.sh
# or, to build somewhere else:
OUT_ROOT=/tmp/rebuild bash scripts/redbench_synthesizer/build_cluster_53_55_combined.sh
```

2. `generate_queryset_from_workload_csv.py` with `--step-hours 2 --freq-suffix _2h
   --sanitize-ceb --queries-json-path <dir>/queries.json` creates `cluster_53_join/` and
   `cluster_55_join/`. The files are named after the matched JOB/CEB queries (e.g.
   `1a1000.sql`) or the query hash, and the CEB-style queries are rewritten to
   `SELECT COUNT(*)`.
3. `scale_frequency.py --factor 2` creates `frequency_time_dependent_2h_x2.json` in each set.
4. `merge_query_folders_sum.py` combines the two sets into `cluster_55_53_combined/`
   (793 queries). The original combination was done with `archive/fix_combined.py`, which
   gives the same SQL files and frequencies.

The script refuses to overwrite existing directories. Its output was checked against the
original query sets: all files of `cluster_53_join` and `cluster_55_join` are byte-identical,
and `cluster_55_53_combined` has identical SQL files and frequencies (only the key order of
its frequency files differs).

### 5. Added JOB/CEB queries (manual)

After the combination, 1,491 JOB/CEB queries (1,488 CEB, 3 JOB) with the same template
numbers as the queries of the workload were added with the help of an LLM. There is no
script for this step. The SQL files are unchanged copies of the JOB/CEB benchmark files that
Redbench uses (`Redbench/output/tmp_matching/imdb/benchmarks/{job,ceb}/`). Each added query
appears in 1–4 time steps; the added frequencies are 2,435 in `_2h` (about 9% of the
total). The result was called `cluster_55_53_combined_ex` (2,284 queries).

### 6. Frequency scaling and renaming

```bash
S=scripts/redbench_synthesizer/scale_frequency.py
Q=01_queries/cluster_55_53_combined_ex/frequency_time_dependent
python $S --input ${Q}_2h.json     --output ${Q}_2h_x2.json     --factor 2  --description-suffix ""
python $S --input ${Q}_2h_x2.json  --output ${Q}_2h_x2_10x.json --factor 10 --description-suffix " (frequencies x10)"
python $S --input ${Q}_2h_x2_10x.json --output ${Q}_2h_x2_50x.json --factor 5 --description-suffix " [x5 of _2h_x2_10x]" --indent none
```

These commands reproduce the three frequency files of `Redbench_synthetic` byte for byte
from the `_2h` file of `cluster_55_53_combined_ex`, which is kept in
`archive/unused_root_20260928/garvage_can/freq/`. The query set was then renamed to
`Redbench_synthetic` (commit `c9ef3ed2`). All Redbench experiments of the paper (RQ1 and
RQ2) use `_2h_x2_50x`.

## Building a new workload

```bash
# 1) SQL files and the frequency file
python scripts/redbench_synthesizer/generate_queryset_from_workload_csv.py \
  --csv-path <workload.csv> --queries-json-path <queries.json> \
  --output-query-dir 01_queries/<query_set> \
  --start <e.g. 2024-05-25T00:00:00> --end <e.g. 2024-05-26T23:59:59> \
  --step-hours <hours per time step> --freq-suffix <suffix> --sanitize-ceb

# 2) Only for the generation strategy: normalize the table names
python scripts/redbench_synthesizer/normalize_queryset_table_versions.py \
  --input-dir 01_queries/<query_set> --in-place
```

The resulting `01_queries/<query_set>/` can then be processed from Phase 1.
