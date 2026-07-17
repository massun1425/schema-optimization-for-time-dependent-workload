#!/usr/bin/env python3
"""Proposed (dynamic parallel: prune+solve) vs Static (utility) optimization time.
Y-axis in seconds; output PDF."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

NS = [10000, 20000, 40000, 60000, 80000, 100000]
labels = [f"{n // 1000}k" for n in NS]


def val(path, keys):
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    s = 0.0
    for k in keys:
        v = d.get(k)
        if v is None:
            return None
        s += v
    return s  # seconds


proposed, static = [], []  # seconds
for N in NS:
    d = f"time_dependent_output/job-ceb-2-q{N}"
    proposed.append(val(f"{d}/td_mv_optimization_result_24_mono.json",
                        ["pruning_time_sec", "solve_time_sec"]))  # dynamic parallel total
    static.append(val(f"{d}/static_mv_optimization_result_24_mono.json",
                      ["execution_time"]))  # utility


def z(x):
    return [0 if v is None else v for v in x]


x = np.arange(len(NS))
w = 0.38
fig, ax = plt.subplots(figsize=(9, 5.5))
ax.bar(x - w / 2, z(proposed), w, color="#4C78A8", label="Proposed")
ax.bar(x + w / 2, z(static), w, color="#54A24B", label="Static")
for i in x:
    if proposed[i] is not None:
        ax.text(i - w / 2, proposed[i] + max(z(proposed)) * 0.01, f"{proposed[i]:.0f}",
                ha="center", va="bottom", fontsize=8)
    else:
        ax.text(i - w / 2, 5, "N/A", ha="center", va="bottom", fontsize=8, color="gray")
    if static[i] is not None:
        ax.text(i + w / 2, static[i] + max(z(proposed)) * 0.01, f"{static[i]:.0f}",
                ha="center", va="bottom", fontsize=8, color="#356b2f")

ax.set_xticks(x)
ax.set_xticklabels(labels)
ax.set_xlabel("Number of queries")
ax.set_ylabel("Optimization time (seconds)")
ax.legend()
ax.grid(axis="y", alpha=0.3)
fig.tight_layout()
out = "progress/scaling_pruning/proposed_vs_static.pdf"
fig.savefig(out)
print("saved", out)
