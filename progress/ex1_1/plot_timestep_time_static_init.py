#!/usr/bin/env python3
"""Per-timestep execution time for result_500M (3 freqs), STATIC includes initial MV build.

Same as plot_timestep_time.py, but for Static the one-time initial MV creation
cost (initial_mv_creation_time) is added to timestep 0. Proposed and Adapt pay
their build/migration cost within each timestep, so they are unchanged.

Freqs: 24_2_10 / 24_mono / 24_peak (one PDF each).
y = timestep_results[t]["total_time"] (= migration.time + query total_time),
    plus initial_mv_creation_time on Static's timestep 0.

Colors/markers aligned with time_dependent_output/ex2_500M_ok/plot_noise.py.
y-axis auto-scales to the data. Output into progress/ex1_1/.
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

D = "time_dependent_output/job-ceb-2/result_500M_ok"
OUT = "progress/ex1_1"
FREQS = ["24_2_10", "24_mono", "24_peak"]

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
# (legend label, filename method token, add initial MV build to timestep 0?)
METHODS = [
    ("Proposed", "dynamic", False),
    ("Adapt", "adaptive_w4", False),
    ("Static", "static", True),
]


def per_timestep_total(path, add_initial_mv=False):
    d = json.load(open(path))
    tr = d["timestep_results"]
    xs = [r.get("timestep_index", i) for i, r in enumerate(tr)]
    ys = [r["total_time"] for r in tr]
    if add_initial_mv:
        init = d.get("initial_mv_creation_time", 0.0) or 0.0
        if ys:
            ys[0] += init  # 初期MV生成時間をタイムステップ0に加算
    return xs, ys


os.makedirs(OUT, exist_ok=True)

for fq in FREQS:
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for label, tok, add_init in METHODS:
        path = f"{D}/benchmark_results_{tok}_{fq}.json"
        if not os.path.exists(path):
            print("MISSING", path)
            continue
        xs, ys = per_timestep_total(path, add_initial_mv=add_init)
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
    ax.set_xticks(range(0, 24, 2))
    ax.tick_params(labelsize=13)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
    ax.legend(fontsize=14)
    # y軸はデータに合わせて自動スケール（上限・下限をフィット）
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    pdf = f"{OUT}/timestep_time_{fq}_static_init.pdf"
    png = f"{OUT}/timestep_time_{fq}_static_init.png"
    fig.savefig(pdf)
    fig.savefig(png, dpi=150)
    plt.close(fig)
    print("saved", pdf)
