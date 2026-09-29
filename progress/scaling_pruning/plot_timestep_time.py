#!/usr/bin/env python3
"""Per-timestep execution time (incl. migration) line charts, one PDF per freq.

Lines: Proposed(dynamic) / Adapt(adaptive w4) / Static(static, not bigsubs).
y = timestep_results[t]["total_time"]  (= migration.time + query total_time).
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

D = "time_dependent_output/job-ceb-2/result_500M"
FREQS = ["24_2_10", "24_mono", "24_peak"]
# (legend label, filename method token, color)
METHODS = [
    ("Proposed", "dynamic", "#4C78A8"),
    ("Adapt", "adaptive_w4", "#F58518"),
    ("Static", "static", "#54A24B"),
]


def per_timestep_total(path):
    d = json.load(open(path))
    tr = d["timestep_results"]
    xs = [r.get("timestep_index", i) for i, r in enumerate(tr)]
    ys = [r["total_time"] for r in tr]
    return xs, ys


for fq in FREQS:
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for label, tok, color in METHODS:
        path = f"{D}/benchmark_results_{tok}_{fq}.json"
        if not os.path.exists(path):
            print("MISSING", path)
            continue
        xs, ys = per_timestep_total(path)
        ax.plot(xs, ys, marker="o", markersize=4, linewidth=1.8, color=color, label=label)
    ax.set_xlabel("Timestep")
    ax.set_ylabel("Execution time")
    ax.legend()
    ax.grid(alpha=0.3)
    ax.set_xticks(range(0, 24, 2))
    fig.tight_layout()
    out = f"{D}/timestep_time_{fq}.pdf"
    fig.savefig(out)
    plt.close(fig)
    print("saved", out)
