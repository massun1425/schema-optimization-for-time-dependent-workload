#!/usr/bin/env python3
"""3-method comparison (dynamic / bigsubs / utility), two x-axes:
   (1) number of queries, (2) number of MV candidates (subexpressions with u>0)."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NS = [10000, 20000, 40000, 60000, 80000, 100000]
# candidate MVs with utility>0 (= what the optimizers actually consider),
# taken from the dynamic-run "候補をフィルタリング: A -> ..." logs.
CAND = {10000: 89909, 20000: 178884, 40000: 356702,
        60000: 534536, 80000: 712370, 100000: 890201}

dyn, big, util = [], [], []
for N in NS:
    dy = json.load(open(f"time_dependent_output/job-ceb-2-q{N}/td_mv_optimization_result_24_mono.json"))
    bg = json.load(open(f"time_dependent_output/job-ceb-2-q{N}/static_bigsubs_optimization_result_24_mono.json"))
    ut = json.load(open(f"time_dependent_output/job-ceb-2-q{N}/static_mv_optimization_result_24_mono.json"))
    dyn.append((dy["pruning_time_sec"] + dy["solve_time_sec"]) / 60.0)
    big.append(bg["execution_time"] / 60.0)
    util.append(ut["execution_time"] / 60.0)


def grouped_bar(xlabels, fname, xtitle):
    x = np.arange(len(NS))
    w = 0.27
    fig, ax = plt.subplots(figsize=(10, 5.8))
    ax.bar(x - w, dyn, w, color="#4C78A8", label="dynamic + CF pruning")
    ax.bar(x, big, w, color="#E45756", label="bigsubs (static, +Gurobi)")
    ax.bar(x + w, util, w, color="#54A24B", label="utility (static)")
    for i in x:
        for off, v, c in [(-w, dyn[i], "#2c4a6e"), (0, big[i], "#9c2b2b"), (w, util[i], "#356b2f")]:
            ax.text(i + off, v + max(dyn) * 0.01, f"{v:.0f}", ha="center", va="bottom", fontsize=8, color=c)
    ax.set_xticks(x)
    ax.set_xticklabels(xlabels)
    ax.set_xlabel(xtitle)
    ax.set_ylabel("Optimization time (minutes)")
    ax.set_title(f"Optimization time vs {xtitle.lower()}: dynamic / bigsubs / utility\n(job-ceb-2 synthetic scaling, B_max=500MB, 24 timesteps)")
    ax.legend(loc="upper left")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(dyn) * 1.15)
    fig.tight_layout()
    fig.savefig(fname, dpi=130)
    print("saved", fname)


grouped_bar([f"{n // 1000}k" for n in NS],
            "progress/scaling_pruning/three_by_queries.png",
            "Number of queries")
grouped_bar([f"{CAND[n] // 1000}k" for n in NS],
            "progress/scaling_pruning/three_by_candidates.png",
            "Number of MV candidates")

print(f"{'N':>8} {'cand':>8} {'dyn(m)':>8} {'big(m)':>8} {'util(m)':>8}")
for i, N in enumerate(NS):
    print(f"{N:>8} {CAND[N]:>8} {dyn[i]:>8.1f} {big[i]:>8.1f} {util[i]:>8.1f}")
