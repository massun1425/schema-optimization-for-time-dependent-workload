#!/usr/bin/env python3
"""Total execution time by storage capacity — Growth and Spikes (_24_peak) workload.

Same figure as plot_capacity.py but for the peak workload pattern in
time_dependent_output/ex4_ok_peak/b{1000,1500,2000}/ (capacity up to 2000MB).
x = capacity (MB), y = total execution time (s) = total_benchmark_time
(query workload time + migration time; Static includes the one-time initial MV
build). Methods: Adapt / Static / Proposed (dynamic). Output PDF into progress/ex4/.
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

BASE = Path("time_dependent_output/ex4_ok_peak")
OUT = Path("progress/ex4")
SUFFIX = "_24_peak"

CAPS = [("b500", "500"), ("b1000", "1000"), ("b1500", "1500"), ("b2000", "2000")]

FILES = {
    "Adapt":    f"benchmark_results_adaptive_w4{SUFFIX}.json",
    "Static":   f"benchmark_results_static{SUFFIX}.json",
    "Proposed": f"benchmark_results_dynamic{SUFFIX}.json",
}
methods = ["Adapt", "Static", "Proposed"]

colors = {
    "Adapt":    "#4272A8",
    "Static":   "#7E9E8E",
    "Proposed": "#A84040",
}


def total_time(cap_dir, fn):
    d = json.load(open(BASE / cap_dir / fn))
    return d["summary"]["total_benchmark_time"]


data = {}
for cap_dir, label in CAPS:
    data[label] = {m: total_time(cap_dir, FILES[m]) for m in methods}

capacities = [label for _, label in CAPS]
values = np.array([[data[cap][m] for m in methods] for cap in capacities])

x = np.arange(len(capacities))
n = len(methods)
width = 0.22
offsets = np.linspace(-(n - 1) / 2, (n - 1) / 2, n) * width

fig, ax = plt.subplots(figsize=(10, 6))

for i, method in enumerate(methods):
    ax.bar(x + offsets[i], values[:, i], width, label=method, color=colors[method])

ax.set_xlabel("Capacity (MB)", fontsize=18)
ax.set_ylabel("Total Execution Time (s)", fontsize=18)
ax.set_title("Growth and Spikes", fontsize=20)
ax.set_xticks(x)
ax.set_xticklabels(capacities, fontsize=18)
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
ax.legend(fontsize=16)
# 差を強調するため y 軸のベースを 0 ではなくデータ下限付近に設定
dmin, dmax = values.min(), values.max()
rng = dmax - dmin
tick = 50000
ymin = max(0, np.floor((dmin - 0.10 * rng) / tick) * tick)
ymax = np.ceil((dmax + 0.08 * rng) / tick) * tick
ax.set_ylim(ymin, ymax)
ax.yaxis.set_major_locator(ticker.MultipleLocator(tick))
ax.tick_params(axis="y", labelsize=16)
ax.set_axisbelow(True)
ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
ax.tick_params(axis="x", which="both", bottom=False, top=False)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "capacity_bar_peak.pdf")
print("Saved: capacity_bar_peak.pdf")

print(f"\n{'Capacity':>8} {'Adapt':>10} {'Static':>10} {'Proposed':>10}")
for cap in capacities:
    print(f"{cap:>8} {data[cap]['Adapt']:>10,.0f} {data[cap]['Static']:>10,.0f} {data[cap]['Proposed']:>10,.0f}")
