#!/usr/bin/env python3
"""Total execution time (query workload + migration) by storage capacity.

Reads time_dependent_output/ex4_ok/b{500,1000,1500,2000}/ and plots a grouped
bar chart: x = capacity (MB), y = total execution time (s) = total_benchmark_time
(query workload time + migration time; Static includes the one-time initial MV
build). Three methods: Adapt / Static / Proposed (dynamic).

Colors are aligned with the other figures. Output PDF (+PNG) into progress/ex4/.
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

BASE = Path("time_dependent_output/ex4_ok")
OUT = Path("progress/ex4")
SUFFIX = "_24_2_10"

# capacity folder -> display label (MB)
CAPS = [("b500", "500"), ("b1000", "1000"), ("b1500", "1500"), ("b2000", "2000")]

# method -> benchmark filename
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


# data[capacity_label][method]
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

ax.set_xlabel("Capacity", fontsize=18)
ax.set_ylabel("Total Execution Time (s)", fontsize=18)
ax.set_xticks(x)
ax.set_xticklabels(capacities, fontsize=18)
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
ax.legend(fontsize=16)
ax.set_ylim(0, values.max() * 1.15)
ax.yaxis.set_major_locator(ticker.MultipleLocator(100000))
ax.tick_params(axis="y", labelsize=16)
ax.set_axisbelow(True)
ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
ax.tick_params(axis="x", which="both", bottom=False, top=False)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "capacity_bar.pdf")
fig.savefig(OUT / "capacity_bar.png", dpi=150)
print("Saved: capacity_bar.pdf and capacity_bar.png")

# summary
print(f"\n{'Capacity':>8} {'Adapt':>10} {'Static':>10} {'Proposed':>10}")
for cap in capacities:
    print(f"{cap:>8} {data[cap]['Adapt']:>10,.0f} {data[cap]['Static']:>10,.0f} {data[cap]['Proposed']:>10,.0f}")
