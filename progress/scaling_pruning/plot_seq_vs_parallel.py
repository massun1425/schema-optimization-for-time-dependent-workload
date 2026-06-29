#!/usr/bin/env python3
"""Charts: sequential vs parallel dynamic pruning (split prune/solve) + static."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NS = [10000, 20000, 40000, 60000, 80000, 100000]
labels = [f"{n // 1000}k" for n in NS]


def g(path, key):
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    v = d.get(key)
    return None if v is None else v / 60.0  # -> minutes


seq_prune, seq_solve, par_prune, par_solve, big, util = [], [], [], [], [], []
for N in NS:
    d = f"time_dependent_output/job-ceb-2-q{N}"
    seq_prune.append(g(f"{d}/td_mv_optimization_result_24_mono_seq.json", "pruning_time_sec"))
    seq_solve.append(g(f"{d}/td_mv_optimization_result_24_mono_seq.json", "solve_time_sec"))
    par_prune.append(g(f"{d}/td_mv_optimization_result_24_mono.json", "pruning_time_sec"))
    par_solve.append(g(f"{d}/td_mv_optimization_result_24_mono.json", "solve_time_sec"))
    big.append(g(f"{d}/static_bigsubs_optimization_result_24_mono.json", "execution_time"))
    util.append(g(f"{d}/static_mv_optimization_result_24_mono.json", "execution_time"))


def v(x):  # None -> 0 for plotting
    return [0 if z is None else z for z in x]


# === Figure 1: dynamic seq vs parallel, stacked (pruning + post-pruning solve) ===
x = np.arange(len(NS))
w = 0.38
fig, ax = plt.subplots(figsize=(11, 6))
sp, ss = v(seq_prune), v(seq_solve)
pp, ps = v(par_prune), v(par_solve)
ax.bar(x - w / 2, sp, w, color="#4C78A8", label="sequential: CF pruning")
ax.bar(x - w / 2, ss, w, bottom=sp, color="#9ecae1", label="sequential: post-pruning solve (all timesteps)")
ax.bar(x + w / 2, pp, w, color="#E45756", label="parallel: CF pruning")
ax.bar(x + w / 2, ps, w, bottom=pp, color="#ff9d98", label="parallel: post-pruning solve (all timesteps)")
for i in x:
    if seq_prune[i] is not None:
        ax.text(i - w / 2, sp[i] + ss[i] + 3, f"{sp[i]+ss[i]:.0f}", ha="center", va="bottom", fontsize=8)
    if par_prune[i] is not None:
        ax.text(i + w / 2, pp[i] + ps[i] + 3, f"{pp[i]+ps[i]:.0f}", ha="center", va="bottom", fontsize=8, color="#9c2b2b")
    else:
        ax.text(i + w / 2, 5, "N/A", ha="center", va="bottom", fontsize=8, color="gray")
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_xlabel("Number of queries"); ax.set_ylabel("Time (minutes)")
ax.set_title("Dynamic optimization: sequential vs parallel pruning\n(stacked = CF pruning + post-pruning all-timesteps solve; job-ceb-2, B_max=500MB, 24 ts)")
ax.legend(loc="upper left", fontsize=9)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout(); fig.savefig("progress/scaling_pruning/seq_vs_parallel_dynamic.png", dpi=130)
print("saved seq_vs_parallel_dynamic.png")

# === Figure 2: all methods total optimization time (grouped) ===
seq_tot = [(sp[i] + ss[i]) if seq_prune[i] is not None else 0 for i in range(len(NS))]
par_tot = [(pp[i] + ps[i]) if par_prune[i] is not None else 0 for i in range(len(NS))]
fig, ax = plt.subplots(figsize=(11, 6))
w2 = 0.2
ax.bar(x - 1.5 * w2, seq_tot, w2, color="#4C78A8", label="dynamic (sequential)")
ax.bar(x - 0.5 * w2, par_tot, w2, color="#E45756", label="dynamic (parallel)")
ax.bar(x + 0.5 * w2, v(big), w2, color="#54A24B", label="bigsubs (static)")
ax.bar(x + 1.5 * w2, v(util), w2, color="#B279A2", label="utility (static)")
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_xlabel("Number of queries"); ax.set_ylabel("Optimization time (minutes)")
ax.set_title("Optimization time by method (dynamic seq/parallel vs static)\n(job-ceb-2 synthetic scaling, B_max=500MB, 24 timesteps)")
ax.legend(loc="upper left", fontsize=9)
ax.grid(axis="y", alpha=0.3)
fig.tight_layout(); fig.savefig("progress/scaling_pruning/all_methods_total.png", dpi=130)
print("saved all_methods_total.png")

# table
print(f"\n{'N':>7} {'seqP':>7} {'seqS':>6} {'parP':>7} {'parS':>6} {'big':>7} {'util':>7} {'prune_speedup':>13}")
for i, N in enumerate(NS):
    su = (seq_prune[i] / par_prune[i]) if (seq_prune[i] and par_prune[i]) else None
    def s(z): return f"{z:.1f}" if z is not None else "-"
    print(f"{N:>7} {s(seq_prune[i]):>7} {s(seq_solve[i]):>6} {s(par_prune[i]):>7} {s(par_solve[i]):>6} "
          f"{s(big[i]):>7} {s(util[i]):>7} {(f'{su:.2f}x' if su else '-'):>13}")
