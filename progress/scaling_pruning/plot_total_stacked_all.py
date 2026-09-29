#!/usr/bin/env python3
"""All workload patterns in ONE stacked bar chart.
Groups = workload patterns; within each group: Proposed/Adapt/Static.
Each bar stacked = query execution (dark, method color) + migration (lighter)."""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mc
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Patch

PATTERNS = [
    ("24_2_10", "time_dependent_output/job-ceb-2/result_500M"),
    ("24_mono", "time_dependent_output/job-ceb-2/result_500M"),
    ("24_peak", "time_dependent_output/job-ceb-2/result_500M"),
    ("2h_x2_50x", "time_dependent_output/ex4/result_b500"),
]
METHODS = [
    ("Proposed", "dynamic", "#4C78A8"),
    ("Adapt", "adaptive_w4", "#F58518"),
    ("Static", "static", "#54A24B"),
]


def lighten(hex_color, amt=0.6):
    c = mc.to_rgb(hex_color)
    return tuple(1 - (1 - x) * (1 - amt) for x in c)


def split(path):
    d = json.load(open(path))
    q = m = 0.0
    for r in d["timestep_results"]:
        q += (r.get("queries", {}) or {}).get("total_time", 0) or 0
        mig = r.get("migration") or {}
        m += (mig.get("time") or 0) if isinstance(mig, dict) else 0
    return q, m


x = np.arange(len(PATTERNS))
w = 0.26
fig, ax = plt.subplots(figsize=(11, 6))
for mi, (label, tok, color) in enumerate(METHODS):
    offset = (mi - 1) * w
    for pi, (fq, D) in enumerate(PATTERNS):
        path = f"{D}/benchmark_results_{tok}_{fq}.json"
        if not os.path.exists(path):
            continue
        q, m = split(path)
        ax.bar(pi + offset, q, w, color=color)
        ax.bar(pi + offset, m, w, bottom=q, color=lighten(color))
        ax.text(pi + offset, q + m, f"{q + m:.0f}", ha="center", va="bottom", fontsize=7, rotation=90)

ax.set_xticks(x)
ax.set_xticklabels([fq for fq, _ in PATTERNS])
ax.set_xlabel("Workload pattern")
ax.set_ylabel("Total execution time (incl. migration)")
handles = [Patch(facecolor=c, label=l) for l, _, c in METHODS]
handles.append(Patch(facecolor=lighten("#999999"), label="Migration (lighter top of each bar)"))
ax.legend(handles=handles, loc="upper left", fontsize=9)
ax.grid(axis="y", alpha=0.3)
ax.margins(y=0.12)
fig.tight_layout()
out = "progress/scaling_pruning/total_time_stacked_all.pdf"
fig.savefig(out)
print("saved", out)
