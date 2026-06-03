#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./run_re_narrowing_matching.sh
# Optional env vars:
#   TOP_N=8 LIMIT_REDSET_ROWS=3000 EVAL_ROOT=output/re_eval ./run_re_narrowing_matching.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ ! -f ../.venv/bin/activate ]]; then
  echo "ERROR: ../.venv/bin/activate が見つかりません" >&2
  exit 1
fi

source ../.venv/bin/activate
export PYTHONPATH="src:src/redbench"

TOP_N="${TOP_N:-8}"
LIMIT_REDSET_ROWS="${LIMIT_REDSET_ROWS:-3000}"
EVAL_ROOT="${EVAL_ROOT:-output/re_eval}"

python - <<'PY'
import glob
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

from redbench.matching.run import generate_workload

root = Path('.')
out = root / 'output'
out.mkdir(exist_ok=True)

# Parameters from env
top_n = int(os.environ.get('TOP_N', '8'))
limit_redset_rows = int(os.environ.get('LIMIT_REDSET_ROWS', '3000'))
eval_root = Path(os.environ.get('EVAL_ROOT', 'output/re_eval'))
eval_root.mkdir(parents=True, exist_ok=True)

parquet = root / 'data/full_serverless.parquet'
if not parquet.exists():
    raise FileNotFoundError(f'Not found: {parquet}')

print(f'[1/4] load parquet: {parquet}')
df = pd.read_parquet(parquet)

if 'created_at' in df.columns:
    ts = pd.to_datetime(df['created_at'], errors='coerce')
elif 'timestamp' in df.columns:
    ts = pd.to_datetime(df['timestamp'], errors='coerce')
else:
    ts = pd.Series(pd.NaT, index=df.index)

if 'cluster_id' not in df.columns:
    if 'instance_id' in df.columns:
        df['cluster_id'] = df['instance_id']
    else:
        df['cluster_id'] = ''

for c in ['database_id', 'feature_fingerprint', 'read_table_ids']:
    if c not in df.columns:
        df[c] = ''
for c in ['num_scans', 'num_joins']:
    if c not in df.columns:
        df[c] = 0

sig = (
    df['feature_fingerprint'].astype(str)
    + '|' + df['num_scans'].fillna(0).astype(int).astype(str)
    + '|' + df['num_joins'].fillna(0).astype(int).astype(str)
    + '|' + df['read_table_ids'].astype(str)
)

g = (
    df.assign(ts=ts)
      .groupby(['cluster_id', 'database_id'], dropna=False)
      .agg(
          total=('cluster_id', 'size'),
          uniq=('feature_fingerprint', lambda s: sig.loc[s.index].nunique()),
          first_ts=('ts', 'min'),
          last_ts=('ts', 'max'),
      )
      .reset_index()
)

g['span_days'] = (g['last_ts'] - g['first_ts']).dt.total_seconds().div(86400).fillna(0)
g['uniq_ratio'] = g['uniq'] / g['total'].replace(0, np.nan)
g['rough_score'] = (
    0.55 * np.log1p(g['uniq'])
    + 0.25 * g['uniq_ratio'].fillna(0)
    + 0.20 * np.log1p(g['span_days'])
)

narrow = g.sort_values('rough_score', ascending=False).head(max(12, top_n)).copy()
narrow_csv = out / 're_narrowing_from_raw_redset.csv'
narrow.to_csv(narrow_csv, index=False)
print(f'[2/4] saved rough narrowing: {narrow_csv}')

# Prepare temporary scanset-matching config from fast.json
base_cfg = root / 'src/redbench/matching/config/fast.json'
cfg = json.loads(base_cfg.read_text())
cfg['matching_method'] = 'scanset'
cfg['limit_redset_rows_read'] = limit_redset_rows
cfg['use_table_versioning'] = False
if cfg.get('support_benchmarks') and isinstance(cfg['support_benchmarks'], list):
    for bench in cfg['support_benchmarks']:
        if isinstance(bench, dict):
            bench['override'] = True

cfg_dir = Path(tempfile.mkdtemp(prefix='rb_cfg_'))
cfg_path = cfg_dir / 'eval_scanset.json'
cfg_path.write_text(json.dumps(cfg, indent=2))

cands = narrow[['cluster_id', 'database_id']].copy()
cands = cands[
    cands['cluster_id'].astype(str).str.fullmatch(r'\d+')
    & cands['database_id'].astype(str).str.fullmatch(r'\d+')
].head(top_n)
rows = []
print(f'[3/4] evaluate top {top_n} candidates with scanset matching')
for _, r in cands.iterrows():
    cid = int(r['cluster_id'])
    did = int(r['database_id'])
    print(f'  - running cluster={cid}, database={did}')
    candidate_eval_root = eval_root / f'cluster_{cid}_db_{did}'
    candidate_eval_root.mkdir(parents=True, exist_ok=True)

    try:
        child_code = """
from redbench.matching.run import generate_workload
generate_workload(
    output_dir=r'__OUTPUT_DIR__',
    redset_path=r'__REDSET_PATH__',
    cluster_id=__CLUSTER_ID__,
    database_id=__DATABASE_ID__,
    config_path=r'__CONFIG_PATH__',
    overwrite_existing=True,
)
""".replace('__OUTPUT_DIR__', str(candidate_eval_root)) \
   .replace('__REDSET_PATH__', str(parquet)) \
   .replace('__CLUSTER_ID__', str(cid)) \
   .replace('__DATABASE_ID__', str(did)) \
   .replace('__CONFIG_PATH__', str(cfg_path))

        env = os.environ.copy()
        env['PYTHONPATH'] = 'src:src/redbench'
        proc = subprocess.run(
            [sys.executable, '-c', child_code],
            cwd=str(root),
            env=env,
            text=True,
            capture_output=True,
        )
        if proc.returncode != 0:
            raise RuntimeError((proc.stderr or proc.stdout or 'generate_workload failed').strip())
    except Exception as e:
        rows.append({
            'cluster_id': cid,
            'database_id': did,
            'score': -1.0,
            'error': str(e),
        })
        continue

    pattern = f'{candidate_eval_root}/generated_workloads/imdb/*/cluster_{cid}/database_{did}/*/stats.json'
    stats_files = glob.glob(pattern)
    if not stats_files:
        rows.append({
            'cluster_id': cid,
            'database_id': did,
            'score': -1.0,
            'error': 'stats.json not found',
        })
        continue

    stats_file = max(stats_files, key=lambda p: Path(p).stat().st_mtime)
    stats = json.loads(Path(stats_file).read_text())

    n_select = stats.get('matched_workload_size', {}).get('num_select_queries', 0) or 0
    not_enough = stats.get('not_enough_instances', 0) or 0
    not_enough_ratio = (not_enough / n_select) if n_select > 0 else 1.0

    mapper = stats.get('scanset_mapper_stats', {}) or {}
    distance_avg = float(mapper.get('distance_avg', mapper.get('avg_distance', 1.0)) or 1.0)

    # Higher score is better
    score = 0.65 * (1.0 - min(max(not_enough_ratio, 0.0), 1.0)) + 0.35 * (1.0 / (1.0 + max(distance_avg, 0.0)))

    rows.append({
        'cluster_id': cid,
        'database_id': did,
        'num_select': int(n_select),
        'not_enough_instances': int(not_enough),
        'not_enough_ratio': float(not_enough_ratio),
        'distance_avg': float(distance_avg),
        'score': float(score),
        'error': '',
    })

res = pd.DataFrame(rows)
if not res.empty:
    res = res.sort_values('score', ascending=False)

json_out = out / 're_narrowing_matching_eval_top8.json'
csv_out = out / 're_narrowing_matching_eval_top8.csv'
json_out.write_text(res.to_json(orient='records', force_ascii=False, indent=2))
res.to_csv(csv_out, index=False)

print(f'[4/4] saved: {json_out}')
print(f'      saved: {csv_out}')
print('\n=== TOP RESULTS ===')
print(res.head(5).to_string(index=False) if not res.empty else 'no results')
PY
