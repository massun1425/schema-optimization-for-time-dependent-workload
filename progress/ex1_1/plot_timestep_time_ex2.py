#!/usr/bin/env python3
"""Per-timestep execution time (incl. migration) line chart for ex2_500M (noise=0).

Lines: Proposed(dynamic) / Adapt(adaptive w4) / Static(static, not bigsubs).
y = timestep_results[t]["total_time"]  (= migration.time + query total_time).

Colors/markers aligned with time_dependent_output/ex2_500M_ok/plot_noise.py.
y-axis auto-scales to the data (upper/lower fit). Output into progress/ex1_1/.
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

D = "time_dependent_output/ex2_500M_ok"
OUT = "progress/ex1_1"
FREQ = "2h_x2_50x"          # noise なし(noise0)の結果

# Palette aligned with plot_noise.py
colors = {
    "Adapt":    "#4272A8",
    "Static":   "#7E9E8E",
    "Proposed": "#A84040",
}
markers = {
    "Adapt":    "o",
    "Static":   "s",
    "Proposed": "^",
}
# (legend label, filename method token)
METHODS = [
    ("Proposed", "dynamic"),
    ("Adapt", "adaptive_w4"),
    ("Static", "static"),
]


def per_timestep_total(path):
    d = json.load(open(path))
    tr = d["timestep_results"]
    xs = [r.get("timestep_index", i) + 1 for i, r in enumerate(tr)]  # 1-based timestep
    ys = [r["total_time"] for r in tr]
    return xs, ys


os.makedirs(OUT, exist_ok=True)

fig, ax = plt.subplots(figsize=(9, 5.2))
for label, tok in METHODS:
    path = f"{D}/benchmark_results_{tok}_{FREQ}.json"
    if not os.path.exists(path):
        print("MISSING", path)
        continue
    xs, ys = per_timestep_total(path)
    ax.plot(
        xs, ys,
        marker=markers[label],
        markersize=6,
        linewidth=2,
        color=colors[label],
        label=label,
    )

ax.set_xlabel("Timestep", fontsize=18)
ax.set_ylabel("Execution Time (s)", fontsize=18)
ax.set_title("Redbench synthetic", fontsize=20)
ax.set_xticks(range(1, 25, 2))
ax.tick_params(labelsize=13)
ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
ax.set_axisbelow(True)
ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
ax.legend(fontsize=14)
# y軸はデータに合わせて自動スケール（上限・下限をフィット）
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

fig.tight_layout()
pdf = f"{OUT}/timestep_time_ex2_500M.pdf"
png = f"{OUT}/timestep_time_ex2_500M.png"
fig.savefig(pdf)
fig.savefig(png, dpi=150)
plt.close(fig)
print("saved", pdf)
