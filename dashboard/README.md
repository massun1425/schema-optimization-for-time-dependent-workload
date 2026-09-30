# Dashboard

A browser dashboard for inspecting optimization and benchmark results: the MVs selected at
each time step, the query trees, the benchmark times over time, comparisons between methods,
and the query frequencies. It is not needed to reproduce the paper. The UI labels are in
Japanese.

## Start

```bash
# from the repository root, with the Python environment of the experiments
cd dashboard
uvicorn dashboard_api:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. On a remote server, forward the port first
(`ssh -L 8000:localhost:8000 <user>@<server>`).

## Selecting results

| Selector | Meaning |
|---|---|
| 結果の場所 (result location) | `time_dependent_output/` (your runs) or `paper_results/` (the results of the paper) |
| フォルダ (folder) | Any folder inside the result location, at any depth (e.g. `rq4/24_mono/b500`); folders without result JSON files (`jobs/`, `log/`, `_stash/`, ...) are not listed |
| 結果ファイル (result file) | Optimization results in the folder; the matching benchmark result is loaded with them |
| クエリセット (query set) | Query set whose data is used for the query trees and the size, cost and utility columns (a folder of `04_migration/`). It is selected automatically when the folder path contains its name (e.g. `rq1/exp1_1/job-ceb-2`); otherwise choose it yourself (job-ceb-2 for `rq1/exp1_2`, `rq3`, `rq4`; Redbench_synthetic for `rq2`) |

## What it reads

The paths are relative to the repository root.

| Data | Location |
|---|---|
| Optimization and benchmark results | the selected folder in `time_dependent_output/` or `paper_results/` |
| Query trees, MV sizes, costs and utilities | `02_json/<query_set>/`, `03_parsed/<query_set>/qp_class.pkl`, `04_migration/<query_set>/` |
| Query frequencies | `01_queries/<query_set>/` |

The dashboard only reads these files.
