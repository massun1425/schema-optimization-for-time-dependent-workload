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

## What it reads

The paths are relative to the repository root.

| Data | Location |
|---|---|
| Optimization and benchmark results | `time_dependent_output/<query_set>/` (where `scripts/run_experiment_normal.py` writes them) and its subfolders named `result_*` |
| Query trees, MV sizes and costs | `03_parsed/<query_set>/qp_class.pkl`, `04_migration/<query_set>/` |
| Queries and frequencies | `01_queries/<query_set>/` |

Select a query set and a result file in the page. The scripts in `paper/` move their results
to `time_dependent_output/rq*/`, which the dashboard does not browse; to inspect one of them,
copy it into `time_dependent_output/<query_set>/` (or a `result_*` subfolder of it).
