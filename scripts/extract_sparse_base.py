#!/usr/bin/env python3
"""One-time extractor: dense parse pickle -> compact sparse base.

The real parse result (e.g. 03_parsed/job-ceb-2/qp_class.pkl, ~2.9GB) stores
u_ij and X as DENSE list-of-lists (X is J*J = 692M cells). Scanning that on
every generation run is wasteful, so we extract the non-zeros ONCE into a small
"sparse base" pickle that the scaling generator can tile quickly.

Usage:
    .venv/bin/python scripts/extract_sparse_base.py --query-set job-ceb-2
"""

import argparse
import pickle
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--query-set", default="job-ceb-2")
    ap.add_argument("--exp-dir", default=".")
    ap.add_argument("--out", default=None, help="output path (default: 03_parsed/<set>/sparse_base.pkl)")
    args = ap.parse_args()

    exp_dir = Path(args.exp_dir)
    parsed_dir = exp_dir / "03_parsed" / args.query_set
    pkl_path = parsed_dir / "qp_class.pkl"
    out_path = Path(args.out) if args.out else parsed_dir / "sparse_base.pkl"

    print(f"loading dense pickle: {pkl_path} ...")
    t0 = time.time()
    with open(pkl_path, "rb") as f:
        qp = pickle.load(f)
    print(f"  loaded in {time.time()-t0:.1f}s")

    u = qp.u_ij
    X = qp.X
    I0 = len(u)
    J0 = len(qp.node_list)
    print(f"I0={I0}, J0={J0}")

    # --- u_ij non-zeros + per-node fan-out (distinct queries with u>0) ---
    print("scanning u_ij for non-zeros + fan-out ...")
    t0 = time.time()
    u_rows = {}
    fanout = [0] * J0
    for i in range(I0):
        row = u[i]
        d = {}
        for j in range(J0):
            v = row[j]
            if v:
                d[j] = v
                if v > 0:
                    fanout[j] += 1
        if d:
            u_rows[i] = d
    u_nnz = sum(len(d) for d in u_rows.values())
    print(f"  u_ij non-zeros={u_nnz} ({time.time()-t0:.1f}s)")

    # --- X non-zeros (adjacency) ---
    print("scanning X (this is the J*J dense scan, one-time) ...")
    t0 = time.time()
    X_adj = {}
    for j in range(J0):
        rowx = X[j]
        s = set()
        for uu in range(J0):
            if rowx[uu]:
                s.add(uu)
        if s:
            X_adj[j] = s
        if (j + 1) % 2000 == 0:
            print(f"    X rows {j+1}/{J0} ({time.time()-t0:.0f}s)")
    x_nnz = sum(len(s) for s in X_adj.values())
    print(f"  X non-zeros={x_nnz} ({time.time()-t0:.1f}s)")

    shared = sum(1 for d in fanout if d >= 2)
    private = sum(1 for d in fanout if d == 1)
    print(f"fan-out: shared(>=2)={shared}, private(==1)={private}, zero={J0 - shared - private}")

    # --- qm dicts that the optimizers actually read ---
    qm = qp.qm
    base = {
        "node_list": list(qp.node_list),
        "I0": I0,
        "J0": J0,
        "u_rows": u_rows,                 # {i: {j: val}}
        "X_adj": X_adj,                   # {j: set(u)}
        "fanout": fanout,                 # per-node distinct-query count (u>0)
        "b_j": list(qp.b_j),
        "q_s_list": [list(r) for r in qp.q_s_list],
        "query_files": list(qp.query_files),  # row-order query names
        # qm subset (sparse dicts) for the utility optimizer
        "subquery_costs": dict(qm.subquery_costs),
        "subquery_positions": {k: [list(p) for p in v] for k, v in qm.subquery_positions.items()},
        "subquery_sizes": dict(qm.subquery_sizes),
        "non_leaf_nodes_map_r": {k: tuple(v) for k, v in qm.non_leaf_nodes_map_r.items()},
    }

    print(f"writing sparse base: {out_path}")
    with open(out_path, "wb") as f:
        pickle.dump(base, f, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"done. size={out_path.stat().st_size/1e6:.1f}MB")


if __name__ == "__main__":
    main()
