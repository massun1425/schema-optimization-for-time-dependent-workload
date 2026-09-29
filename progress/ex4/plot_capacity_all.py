#!/usr/bin/env python3
"""Combined capacity figure: 3 workload patterns side by side, one shared legend.

Panels: Cycles / Evolution and Stagnation / Growth and Spikes.
x = capacity (MB), y = total execution time (s) shown in 'k' (thousands) to avoid
long zero strings. Each panel has an independent, non-zero y-base to emphasize
differences. Larger fonts; a single legend for the whole figure. Output PDF (+PNG).
"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

OUT = Path("progress/ex4")

# (title, base folder, suffix)
PANELS = [
    ("Cycles", "time_dependent_output/ex4_ok_cycle", "_24_2_10"),
    ("Evolution and Stagnation", "time_dependent_output/ex4_ok_mono", "_24_mono"),
    ("Growth and Spikes", "time_dependent_output/ex4_ok_peak", "_24_peak"),
]
CAPS = [("b500", "500"), ("b1000", "1000"), ("b1500", "1500"), ("b2000", "2000")]
methods = ["Adapt", "Static", "Proposed"]
FILES = {
    "Adapt":    "benchmark_results_adaptive_w4{s}.json",
    "Static":   "benchmark_results_static{s}.json",
    "Proposed": "benchmark_results_dynamic{s}.json",
}
colors = {"Adapt": "#4272A8", "Static": "#7E9E8E", "Proposed": "#A84040"}


def total_time(base, cap_dir, fn):
    return json.load(open(f"{base}/{cap_dir}/{fn}"))["summary"]["total_benchmark_time"]


fig, axes = plt.subplots(1, 3, figsize=(20, 6.5))

bar_handles = None
for ax, (title, base, suf) in zip(axes, PANELS):
    values = np.array([[total_time(base, cd, FILES[m].format(s=suf)) for m in methods]
                        for cd, _ in CAPS])
    caps = [lbl for _, lbl in CAPS]
    x = np.arange(len(caps))
    n = len(methods)
    width = 0.24
    offsets = np.linspace(-(n - 1) / 2, (n - 1) / 2, n) * width

    hs = []
    for i, m in enumerate(methods):
        h = ax.bar(x + offsets[i], values[:, i], width, label=m, color=colors[m])
        hs.append(h)
    if bar_handles is None:
        bar_handles = hs

    ax.set_title(title, fontsize=24)
    ax.set_xlabel("Capacity (MB)", fontsize=22)
    ax.set_xticks(x)
    ax.set_xticklabels(caps, fontsize=19)
    # y 軸: k 表記、ベースを 0 でなくデータ下限付近に
    dmin, dmax = values.min(), values.max()
    rng = dmax - dmin
    ymin = max(0, dmin - 0.12 * rng)
    ymax = dmax + 0.08 * rng
    ax.set_ylim(ymin, ymax)
    ax.yaxis.set_major_locator(ticker.MaxNLocator(6))
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
    ax.tick_params(axis="y", labelsize=18)
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
    ax.tick_params(axis="x", which="both", bottom=False, top=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

axes[0].set_ylabel("Total Execution Time (s)", fontsize=22)

# 全体で1つの凡例（上部中央）
fig.legend([h[0] for h in bar_handles], methods,
           loc="upper center", ncol=3, fontsize=22,
           frameon=True, bbox_to_anchor=(0.5, 1.06))

fig.tight_layout(rect=[0, 0, 1, 0.94])
OUT.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT / "capacity_bar_all.pdf", bbox_inches="tight")
fig.savefig(OUT / "capacity_bar_all.png", dpi=150, bbox_inches="tight")
print("Saved: capacity_bar_all.pdf and capacity_bar_all.png")
