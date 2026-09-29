#!/usr/bin/env python3
"""Plot optimization time vs query count (pruning + ILP solve) from result JSONs."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NS = [10000, 20000, 40000, 60000, 80000, 100000]
prune, solve, total_clean = [], [], []
for N in NS:
    f = f"time_dependent_output/job-ceb-2-q{N}/td_mv_optimization_result_24_mono.json"
    d = json.load(open(f))
    p = d["pruning_time_sec"]
    s = d["solve_time_sec"]
    prune.append(p / 60.0)      # -> minutes
    solve.append(s / 60.0)
    total_clean.append((p + s) / 60.0)

labels = [f"{n // 1000}k" for n in NS]
x = range(len(NS))

fig, ax = plt.subplots(figsize=(9, 5.5))
b1 = ax.bar(x, prune, color="#4C78A8", label="CF Pruning")
b2 = ax.bar(x, solve, bottom=prune, color="#F58518", label="ILP solve (Gurobi)")

for i in x:
    ax.text(i, total_clean[i] + max(total_clean) * 0.01, f"{total_clean[i]:.0f}m",
            ha="center", va="bottom", fontsize=10, fontweight="bold")

ax.set_xticks(list(x))
ax.set_xticklabels(labels)
ax.set_xlabel("Number of queries")
ax.set_ylabel("Optimization time (minutes)")
ax.set_title("Pruning + Dynamic optimization time vs query count\n(job-ceb-2 synthetic scaling, B_max=500MB, 24 timesteps)")
ax.legend(loc="upper left")
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, max(total_clean) * 1.12)
fig.tight_layout()

out = "progress/scaling_pruning/optimization_time.png"
fig.savefig(out, dpi=130)
print("saved", out)

# also print a compact table
print(f"{'N':>8} {'prune(m)':>10} {'solve(m)':>10} {'total(m)':>10}")
for i, N in enumerate(NS):
    print(f"{N:>8} {prune[i]:>10.1f} {solve[i]:>10.1f} {total_clean[i]:>10.1f}")
