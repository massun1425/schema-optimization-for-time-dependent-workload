#!/usr/bin/env python3
"""Per-workload total execution time, stacked = query execution + migration.

One PDF per workload pattern. Bar color per method matches the per-timestep
line charts (Proposed/Adapt/Static); the migration segment uses a lighter tint
of the same color. y = raw benchmark total_time (same units as the line charts).
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mc
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

METHODS = [
    ("Proposed", "dynamic", "#4C78A8"),
    ("Adapt", "adaptive_w4", "#F58518"),
    ("Static", "static", "#54A24B"),
]
TARGETS = [
    ("time_dependent_output/job-ceb-2/result_500M", "24_2_10"),
    ("time_dependent_output/job-ceb-2/result_500M", "24_mono"),
    ("time_dependent_output/job-ceb-2/result_500M", "24_peak"),
    ("time_dependent_output/ex4/result_b500", "2h_x2_50x"),
]


def lighten(hex_color, amt=0.6):
    c = mc.to_rgb(hex_color)
    return tuple(1 - (1 - x) * (1 - amt) for x in c)  # blend toward white


def split(path):
    """Return (query_time, migration_time) summed over timesteps."""
    d = json.load(open(path))
    q = m = 0.0
    for r in d["timestep_results"]:
        q += (r.get("queries", {}) or {}).get("total_time", 0) or 0
        mig = r.get("migration") or {}
        m += (mig.get("time") or 0) if isinstance(mig, dict) else 0
    return q, m


for D, fq in TARGETS:
    fig, ax = plt.subplots(figsize=(7, 5.5))
    xticklabels = []
    for i, (label, tok, color) in enumerate(METHODS):
        path = f"{D}/benchmark_results_{tok}_{fq}.json"
        if not os.path.exists(path):
            xticklabels.append(label)
            continue
        q, m = split(path)
        ax.bar(i, q, color=color)                          # query execution (dark)
        ax.bar(i, m, bottom=q, color=lighten(color))       # migration (lighter)
        ax.text(i, q + m + max(q + m, 1) * 0.01, f"{q + m:.0f}", ha="center", va="bottom", fontsize=9)
        xticklabels.append(label)
    ax.set_xticks(range(len(METHODS)))
    ax.set_xticklabels(xticklabels)
    ax.set_ylabel("Total execution time (incl. migration)")
    # legend explaining the dark/light shading convention
    ax.legend(handles=[
        Patch(facecolor="#555555", label="Query execution"),
        Patch(facecolor=lighten("#555555"), label="Migration"),
    ], loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    out = f"{D}/total_time_stacked_{fq}.pdf"
    fig.savefig(out)
    plt.close(fig)
    print("saved", out)
