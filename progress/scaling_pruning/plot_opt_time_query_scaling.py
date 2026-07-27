#!/usr/bin/env python3
"""Optimization time vs. number of queries (24 timesteps, job-ceb-2-qN).

Compares three methods:
  - Static        : static_mv_optimization_result_24_mono.json   (execution_time)
  - With Pruning  : td_mv_optimization_result_24_mono_wp.json     (phase_time_sec)
  - No Pruning    : td_mv_optimization_result_24_mono.json        (phase_time_sec)

No-Pruning runs were capped at 24h; sizes without a result file timed out (DNF)
and are drawn as a hatched bar reaching the 24h ceiling with a "DNF" label.

Y-axis: optimization time in hours (0..24). X-axis: number of queries.
Outputs both PDF (deliverable) and PNG (for markdown embedding).
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

NS = [20000, 40000, 60000, 80000, 100000]
labels = [f"{n // 1000}k" for n in NS]
HOUR = 3600.0
Y_MAX = 24  # hours

colors = {
    "Static":       "#7E9E8E",  # green  (same as ex1_1 Static)
    "With Pruning": "#A84040",  # red    (same as ex1_1 Proposed)
    "No Pruning":   "#DD8452",  # orange (unused elsewhere)
}


def read_val(path, keys):
    """Return the first present key value (seconds), or None if file/keys absent."""
    if not os.path.exists(path):
        return None
    d = json.load(open(path))
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


static, with_pruning, no_pruning = [], [], []
for n in NS:
    base = f"time_dependent_output/job-ceb-2-q{n}"
    static.append(read_val(f"{base}/static_mv_optimization_result_24_mono.json",
                            ["execution_time"]))
    with_pruning.append(read_val(f"{base}/td_mv_optimization_result_24_mono_wp.json",
                                 ["phase_time_sec"]))
    # No-pruning: plain filename. Missing -> DNF (timed out at 24h).
    no_pruning.append(read_val(f"{base}/td_mv_optimization_result_24_mono.json",
                               ["phase_time_sec"]))


def to_hours(vals):
    return [None if v is None else v / HOUR for v in vals]


static_h = to_hours(static)
wp_h = to_hours(with_pruning)
np_h = to_hours(no_pruning)

# --- plot ----------------------------------------------------------------
x = np.arange(len(NS))
w = 0.26
fig, ax = plt.subplots(figsize=(9, 5.5))

series = [
    ("Static", static_h, -w),
    ("With Pruning", wp_h, 0.0),
    ("No Pruning", np_h, w),
]

for name, ys, off in series:
    for i, y in enumerate(ys):
        xi = x[i] + off
        if y is None:
            # DNF: hatched bar to the ceiling + label (not shown in legend)
            ax.bar(xi, Y_MAX, w, color=colors[name], alpha=0.30,
                   hatch="///", edgecolor=colors[name], linewidth=1.0)
            ax.text(xi, Y_MAX * 0.55, "DNF", ha="center", va="center",
                    rotation=90, fontsize=10, fontweight="bold",
                    color=colors[name])
        else:
            ax.bar(xi, y, w, color=colors[name])

ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=13)
ax.set_xlabel("Number of queries", fontsize=16)
ax.set_ylabel("Optimization time (hours)", fontsize=16)
ax.set_ylim(0, Y_MAX)
ax.set_yticks(range(0, Y_MAX + 1, 4))
ax.axhline(Y_MAX, color="gray", linestyle=":", linewidth=1.0)
ax.set_axisbelow(True)
ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# legend (proxy handles) — DNF is not explained in the legend
handles = [mpatches.Patch(color=colors[n], label=n)
           for n, _, _ in series]
ax.legend(handles=handles, fontsize=12, loc="upper left")

fig.tight_layout()
pdf = "progress/scaling_pruning/opt_time_query_scaling.pdf"
png = "progress/scaling_pruning/opt_time_query_scaling.png"
fig.savefig(pdf)
fig.savefig(png, dpi=150)
print("saved", pdf, "and", png)

# summary table to stdout
print(f"\n{'N':>8} {'Static(h)':>10} {'WithPrune(h)':>13} {'NoPrune(h)':>12}")
for i, n in enumerate(NS):
    def f(v):
        return "DNF" if v is None else f"{v:.2f}"
    print(f"{n:>8} {f(static_h[i]):>10} {f(wp_h[i]):>13} {f(np_h[i]):>12}")
