#!/usr/bin/env python3
"""Generate a synthetic, K-fold scaled query set by block-tiling the real
job-ceb-2 structure (sparse). For optimizer SCALABILITY testing only --
no benchmark/DB execution involved.

Approach (decided): copy the real instance K times.
  - Nodes with fan-out >= 2 ("shared") are kept GLOBAL (one copy, referenced by
    all blocks) -> reproduces the real low-sharing / near-linear J growth.
  - Nodes with fan-out <= 1 ("private") are CLONED per block (id suffix __rk).
  - Within each block, sharing & containment (X) are exactly the real ones.
  - Costs / sizes / utilities are perturbed by +/-eps on cloned blocks to break
    symmetry (so Gurobi cannot exploit identical sub-problems).
  - Frequencies reuse an existing pattern (e.g. 24_mono); NOT newly invented.

Outputs (a NEW query set; originals untouched):
  03_parsed/<newset>/qp_class.pkl                         (SparseQP)
  04_migration/<newset>/simple_migration_costs.json       (scaled, "[]" recipes)
  01_queries/<newset>/frequency_time_dependent<suffix>.json

Usage:
  .venv/bin/python scripts/generate_synthetic_scaling.py \
      --base-set job-ceb-2 --K 8 --freq-suffix _24_mono
"""

import argparse
import json
import pickle
import random
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.sparse_structures import SparseMatrix, SparseX, SparseQM, SparseQP  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-set", default="job-ceb-2", help="source query set")
    ap.add_argument("--K", type=int, default=None, help="tiling factor (K=8 ~ 20k queries)")
    ap.add_argument("--queries", type=int, default=None,
                    help="exact target query count; tiles ceil(N/I0) blocks then trims to N "
                         "(orphaned private nodes carry zero utility -> auto-excluded by the optimizer)")
    ap.add_argument("--out-set", default=None, help="output set name (default <base>-x<K> or <base>-q<N>)")
    ap.add_argument("--freq-suffix", default="_24_mono", help="frequency pattern to reuse")
    ap.add_argument("--eps", type=float, default=0.05, help="+/- perturbation on cloned blocks")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--exp-dir", default=".")
    args = ap.parse_args()

    rng = random.Random(args.seed)
    exp_dir = Path(args.exp_dir)
    base_set = args.base_set
    eps = args.eps
    if (args.K is None) == (args.queries is None):
        ap.error("specify exactly one of --K or --queries")

    base_path = exp_dir / "03_parsed" / base_set / "sparse_base.pkl"
    cost_path = exp_dir / "04_migration" / base_set / "simple_migration_costs.json"
    freq_path = exp_dir / "01_queries" / base_set / f"frequency_time_dependent{args.freq_suffix}.json"

    print(f"loading sparse base: {base_path}")
    with open(base_path, "rb") as f:
        base = pickle.load(f)
    print(f"loading cost json: {cost_path}")
    with open(cost_path, "r", encoding="utf-8") as f:
        cost_raw = json.load(f)
    print(f"loading frequency: {freq_path}")
    with open(freq_path, "r", encoding="utf-8") as f:
        freq_data = json.load(f)

    node_list0 = base["node_list"]
    I0, J0 = base["I0"], base["J0"]
    u_rows = base["u_rows"]
    X_adj = base["X_adj"]
    fanout = base["fanout"]
    b_j0 = base["b_j"]
    q_s_list0 = base["q_s_list"]
    query_files0 = base["query_files"]  # row-order stems
    sq_costs0 = base["subquery_costs"]
    sq_sizes0 = base["subquery_sizes"]
    nlmr0 = base["non_leaf_nodes_map_r"]

    # --- determine number of blocks K and exact query count newI ---
    import math
    if args.queries is not None:
        newI = args.queries
        K = math.ceil(newI / I0)
        out_set = args.out_set or f"{base_set}-q{newI}"
    else:
        K = args.K
        newI = K * I0
        out_set = args.out_set or f"{base_set}-x{K}"

    # --- classify shared (fan-out>=2, global) vs private (<=1, cloned) ---
    shared_mask = [d >= 2 for d in fanout]
    private_idx = [j for j in range(J0) if not shared_mask[j]]
    priv_pos = {j: p for p, j in enumerate(private_idx)}
    P = len(private_idx)
    newJ = J0 + (K - 1) * P
    trimmed = K * I0 - newI
    print(f"K={K}: shared={J0 - P}, private={P} -> newI={newI} (trimmed {trimmed} from last block), newJ(nominal)={newJ}")

    def newidx(k: int, j: int) -> int:
        """Map original node index j to its index in block k."""
        if k == 0 or shared_mask[j]:
            return j
        return J0 + (k - 1) * P + priv_pos[j]

    def pert(k: int) -> float:
        """Perturbation factor: exact for block 0, +/-eps for cloned blocks."""
        return 1.0 if k == 0 else (1.0 + rng.uniform(-eps, eps))

    # --- new node_list ---
    print("building node_list ...")
    new_node_list = list(node_list0)  # block 0 keeps original ids/indices
    for k in range(1, K):
        for j in private_idx:
            new_node_list.append(f"{node_list0[j]}__r{k}")
    assert len(new_node_list) == newJ

    # --- new u_ij (sparse), q_s_list, b_j ---
    print("tiling u_ij / q_s_list ...")
    t0 = time.time()
    new_rows = {}
    new_q_s = [None] * newI
    for k in range(K):
        for i in range(I0):
            ni = k * I0 + i
            if ni >= newI:  # trim last block to exact target
                break
            d = u_rows.get(i)
            if d:
                f = pert(k)
                new_rows[ni] = {newidx(k, j): val * f for j, val in d.items()}
            new_q_s[ni] = [newidx(k, j) for j in q_s_list0[i]]
    print(f"  u nnz={sum(len(d) for d in new_rows.values())} ({time.time()-t0:.1f}s)")

    new_b = [0.0] * newJ
    for j in range(J0):
        new_b[j] = b_j0[j]
    for k in range(1, K):
        for j in private_idx:
            new_b[newidx(k, j)] = b_j0[j] * pert(k)

    # --- new X (sparse adjacency) ---
    print("tiling X ...")
    t0 = time.time()
    new_adj = {}
    for k in range(K):
        for j, sset in X_adj.items():
            nj = newidx(k, j)
            tgt = new_adj.setdefault(nj, set())
            for uu in sset:
                tgt.add(newidx(k, uu))
    print(f"  X nnz={sum(len(s) for s in new_adj.values())} ({time.time()-t0:.1f}s)")

    # --- new cost json (only "[]" full-build recipe; that's all loaders read) ---
    print("tiling cost json ...")
    new_cost = {}
    missing_cost = 0
    for k in range(K):
        f = pert(k)
        for j in range(J0):
            if k > 0 and shared_mask[j]:
                continue  # shared node already emitted in block 0
            orig_id = node_list0[j]
            new_id = orig_id if (k == 0 or shared_mask[j]) else f"{orig_id}__r{k}"
            recipe = cost_raw.get(orig_id, {})
            fb = recipe.get("[]")
            if fb is None:
                missing_cost += 1
                new_cost[new_id] = {"[]": {"cost": float("inf"), "utility": float("inf"), "size": 1}}
                continue
            new_cost[new_id] = {"[]": {
                "cost": float(fb.get("cost", 0.0)) * f,
                "utility": float(fb.get("utility", fb.get("cost", 0.0))) * f,
                "size": float(fb.get("size", 1)) * f,
            }}
    if missing_cost:
        print(f"  WARNING: {missing_cost} nodes had no full-build recipe")

    # --- qm subset for utility optimizer (best-effort) ---
    print("building qm subset (for utility) ...")
    new_sq_costs, new_sq_sizes, new_sq_pos, new_nlmr = {}, {}, {}, {}
    for k in range(K):
        f = pert(k)
        for j in range(J0):
            if k > 0 and shared_mask[j]:
                continue
            orig_id = node_list0[j]
            new_id = orig_id if (k == 0 or shared_mask[j]) else f"{orig_id}__r{k}"
            new_sq_costs[new_id] = sq_costs0.get(orig_id, 0.0) * f
            new_sq_sizes[new_id] = sq_sizes0.get(orig_id, 0) * f
            if orig_id in nlmr0:
                new_nlmr[new_id] = tuple(
                    (child if (shared_mask_by_id(child, node_list0, shared_mask)) else f"{child}__r{k}")
                    if k > 0 else child
                    for child in nlmr0[orig_id]
                )
    # subquery_positions: derived from the tiled incidence (preserves usage count)
    for ni, d in new_rows.items():
        for nj in d:
            new_sq_pos.setdefault(new_node_list[nj], []).append([ni, 0])

    # --- new frequency (reuse pattern; align names to row order by zero-padded id) ---
    print("tiling frequency ...")
    queries0 = freq_data.get("queries", {})
    # map stem -> freq list
    freq_by_stem = {}
    for name, vals in queries0.items():
        stem = name[:-4] if name.endswith(".sql") else name
        freq_by_stem[stem] = vals
    T = len(next(iter(queries0.values()))) if queries0 else 0
    new_queries = {}
    miss_freq = 0
    for k in range(K):
        for i in range(I0):
            ni = k * I0 + i
            if ni >= newI:  # trim last block to exact target
                break
            stem = query_files0[i]
            vals = freq_by_stem.get(stem)
            if vals is None:
                miss_freq += 1
                vals = [0] * T
            # name sorts (naturally) exactly in ni order -> aligns with u rows
            new_queries[f"q{ni:07d}.sql"] = list(vals)
    if miss_freq:
        print(f"  WARNING: {miss_freq} rows had no frequency entry (zero-filled)")
    new_freq = {
        "description": f"synthetic x{K} tiling of {base_set}{args.freq_suffix}",
        "note": "scalability test only; not a real workload",
        "queries": new_queries,
    }

    # --- assemble SparseQP ---
    qp = SparseQP(
        node_list=new_node_list,
        u_ij=SparseMatrix(new_rows, newI, newJ),
        X=SparseX(new_adj, newJ),
        s_num=newJ,
        qm=SparseQM(new_sq_costs, new_sq_pos, new_sq_sizes, new_nlmr),
        q_s_list=new_q_s,
        b_j=new_b,
        query_files=[f"q{g:07d}" for g in range(newI)],
    )

    # --- write outputs ---
    out_parsed = exp_dir / "03_parsed" / out_set
    out_mig = exp_dir / "04_migration" / out_set
    out_q = exp_dir / "01_queries" / out_set
    for d in (out_parsed, out_mig, out_q):
        d.mkdir(parents=True, exist_ok=True)

    pkl_out = out_parsed / "qp_class.pkl"
    print(f"writing {pkl_out}")
    with open(pkl_out, "wb") as f:
        pickle.dump(qp, f, protocol=pickle.HIGHEST_PROTOCOL)

    cost_out = out_mig / "simple_migration_costs.json"
    print(f"writing {cost_out}")
    with open(cost_out, "w", encoding="utf-8") as f:
        json.dump(new_cost, f)

    freq_out = out_q / f"frequency_time_dependent{args.freq_suffix}.json"
    print(f"writing {freq_out}")
    with open(freq_out, "w", encoding="utf-8") as f:
        json.dump(new_freq, f)

    print(f"\nDONE: set='{out_set}'  I={newI}  J={newJ}  "
          f"u_nnz={qp.u_ij.nnz()}  X_nnz={qp.X.nnz()}  pkl={pkl_out.stat().st_size/1e6:.1f}MB")


def shared_mask_by_id(child_id, node_list0, shared_mask):
    """Return True if child node id is a shared (global) node."""
    # node ids are unique strings; build index lazily on first use
    if not hasattr(shared_mask_by_id, "_idx"):
        shared_mask_by_id._idx = {nid: j for j, nid in enumerate(node_list0)}
    j = shared_mask_by_id._idx.get(child_id)
    return bool(j is not None and shared_mask[j])


if __name__ == "__main__":
    main()
