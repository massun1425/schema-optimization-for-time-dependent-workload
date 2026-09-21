#!/usr/bin/env python3
"""Optimization time vs. number of timesteps: Proposed (w/ pruning) vs Proposed (w/o pruning).

Data: time_dependent_output/job-ceb-2/result_scaling_time_ok/
      td_mv_optimization_result_{TS}_mono_{wp,wo}.json
  wp = with CF pruning, wo = without pruning (full candidate ILP).
Optimization time = phase_time_sec (whole Phase-6 wall time:
  wp = pruning + ILP solve + overhead, wo = ILP solve + overhead).

Grouped bar chart; y-axis capped at ylim, values above it annotated as text
(style follows the reference plot_timestep.py). Outputs PDF (+PNG) and a
timestep.json summary into progress/scaling_timestep/.
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

DIR = Path(__file__).parent
SRC = Path("time_dependent_output/job-ceb-2/result_scaling_time_ok")
TS = [12, 18, 24, 30, 36, 42]
METHODS = ["Proposed (w/ pruning)", "Proposed (w/o pruning)"]  # order = bar order


def phase_time(ts, tag):
    d = json.load(open(SRC / f"td_mv_optimization_result_{ts}_mono_{tag}.json"))
    return d["phase_time_sec"]


# data[timestep_label][method] = optimization time (s)
data = {}
for ts in TS:
    data[str(ts)] = {
        "Proposed (w/ pruning)": phase_time(ts, "wp"),
        "Proposed (w/o pruning)": phase_time(ts, "wo"),
    }

# save summary json (mirrors reference's timestep.json)
with open(DIR / "timestep.json", "w") as f:
    json.dump(data, f, indent=2)

# --- plot ----------------------------------------------------------------
timesteps = list(data.keys())
methods = METHODS
labels = [m for m in methods]
values = np.array([[data[ts][m] for m in methods] for ts in timesteps])

x = np.arange(len(timesteps))
n = len(methods)
width = 0.32
offsets = np.linspace(-(n - 1) / 2, (n - 1) / 2, n) * width

# colors matched to the pruning-comparison figures:
#   Proposed (w/ pruning) = red (ex1_1 Proposed), Proposed (w/o pruning) = orange (unused elsewhere)
colors = ["#A84040", "#DD8452"]

# height matched to the ex1_1 aspect ratio (9:5.2): 14 * 5.2/9 ≈ 8.09
fig, ax = plt.subplots(figsize=(14, 8.09))

# y軸は全バーが収まるように自動で引き伸ばす
ylim = values.max() * 1.10

for i, (label, color) in enumerate(zip(labels, colors)):
    ax.bar(x + offsets[i], values[:, i], width, label=label, color=color)

ax.set_xlabel("Number of Timesteps", fontsize=22)
ax.set_ylabel("Optimization Time (s)", fontsize=22)
ax.set_xticks(x)
ax.set_xticklabels(timesteps, fontsize=20)
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
ax.tick_params(axis="y", labelsize=18)
ax.legend(fontsize=18)
ax.set_ylim(0, ylim)
ax.yaxis.set_major_locator(ticker.MultipleLocator(500))
ax.set_axisbelow(True)
ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)

plt.tight_layout()
plt.savefig(DIR / "timestep_bar.pdf")
plt.savefig(DIR / "timestep_bar.png", dpi=150)
print("Saved: timestep_bar.pdf and timestep_bar.png")

# stdout summary
print(f"\n{'TS':>4} {'WithPruning(s)':>15} {'NoPruning(s)':>13}")
for ts in TS:
    print(f"{ts:>4} {data[str(ts)]['Proposed (w/ pruning)']:>15,.1f} {data[str(ts)]['Proposed (w/o pruning)']:>13,.1f}")
