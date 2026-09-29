#!/usr/bin/env python3
"""Compare optimization time: dynamic(+pruning) vs bigsubs(static), per query count."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NS = [10000, 20000, 40000, 60000, 80000, 100000]
dyn, big, big_iter = [], [], []
for N in NS:
    dy = json.load(open(f"time_dependent_output/job-ceb-2-q{N}/td_mv_optimization_result_24_mono.json"))
    bg = json.load(open(f"time_dependent_output/job-ceb-2-q{N}/static_bigsubs_optimization_result_24_mono.json"))
    dyn.append((dy["pruning_time_sec"] + dy["solve_time_sec"]) / 60.0)  # minutes
    big.append(bg["execution_time"] / 60.0)
    big_iter.append(bg.get("iterations"))

labels = [f"{n // 1000}k" for n in NS]
x = np.arange(len(NS))
w = 0.38

fig, ax = plt.subplots(figsize=(10, 5.8))
b1 = ax.bar(x - w / 2, dyn, w, color="#4C78A8", label="dynamic + CF pruning (prune+solve)")
b2 = ax.bar(x + w / 2, big, w, color="#E45756", label="bigsubs (static, execution_time)")

for i in x:
    ax.text(i - w / 2, dyn[i] + 3, f"{dyn[i]:.0f}", ha="center", va="bottom", fontsize=9)
    ax.text(i + w / 2, big[i] + 3, f"{big[i]:.0f}", ha="center", va="bottom", fontsize=9, color="#9c2b2b")

ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_xlabel("Number of queries")
ax.set_ylabel("Optimization time (minutes)")
ax.set_title("Optimization time vs query count: dynamic(+pruning) vs bigsubs\n(job-ceb-2 synthetic scaling, B_max=500MB, 24 timesteps)")
ax.legend(loc="upper left")
ax.grid(axis="y", alpha=0.3)
ax.set_ylim(0, max(dyn) * 1.15)
fig.tight_layout()
fig.savefig("progress/scaling_pruning/compare_dyn_bigsubs.png", dpi=130)
print("saved progress/scaling_pruning/compare_dyn_bigsubs.png")

print(f"{'N':>8} {'dynamic(m)':>11} {'bigsubs(m)':>11} {'big_iter':>9} {'speedup x':>10}")
for i, N in enumerate(NS):
    print(f"{N:>8} {dyn[i]:>11.1f} {big[i]:>11.1f} {str(big_iter[i]):>9} {dyn[i]/big[i]:>9.1f}x")
