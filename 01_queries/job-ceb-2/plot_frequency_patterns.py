#!/usr/bin/env python3
"""Frequency (execution-count) change patterns for the 3 workload patterns.

Draws Group A / Group B representative curves (x = timestep, y = execution
count) for each of the three job-ceb-2 frequency files, following the reference
plot style. Group A = first odd-numbered query (e.g. 1a.sql),
Group B = first even-numbered query (e.g. 2a.sql); these are the two canonical
anti-phase patterns in each file.

Output PDFs (+PNG) are written next to this script (01_queries/job-ceb-2/).
"""
import json
import re
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

DATA_DIR = os.path.dirname(os.path.abspath(__file__))

# (frequency file, display title)
FILES = [
    ("frequency_time_dependent_24_2_10.json", "Cycles"),
    ("frequency_time_dependent_24_mono.json", "Evolution and Stagnation"),
    ("frequency_time_dependent_24_peak.json", "Growth and Spikes"),
]

COLOR_A = "tab:blue"
COLOR_B = "tab:red"

FONT_SIZE = 20
plt.rcParams.update({
    "font.size": FONT_SIZE,
    "axes.titlesize": FONT_SIZE + 2,
    "axes.labelsize": FONT_SIZE,
    "xtick.labelsize": FONT_SIZE - 2,
    "ytick.labelsize": FONT_SIZE - 2,
    "legend.fontsize": FONT_SIZE - 2,
})


def query_number(key: str) -> int:
    return int(re.match(r"(\d+)", key).group(1))


for filename, title in FILES:
    path = os.path.join(DATA_DIR, filename)
    data = json.load(open(path))
    queries = data["queries"]

    fig, ax = plt.subplots(figsize=(12, 5))
    fig.suptitle(title, fontsize=FONT_SIZE + 2)

    for group, color in [("odd", COLOR_A), ("even", COLOR_B)]:
        parity = 1 if group == "odd" else 0
        keys = sorted(
            [k for k in queries if re.match(r"(\d+)", k) and query_number(k) % 2 == parity],
            key=query_number,
        )
        key = keys[0]
        freqs = queries[key]
        timesteps = list(range(1, len(freqs) + 1))
        ax.plot(timesteps, freqs, color=color, linewidth=2.0)

    legend_handles = [
        mlines.Line2D([], [], color=COLOR_A, linewidth=2.5, label="Group A "),
        mlines.Line2D([], [], color=COLOR_B, linewidth=2.5, label="Group B "),
    ]
    ax.legend(handles=legend_handles, loc="upper left")
    ax.set_xlabel("Timestep")
    ax.set_ylabel("Execution count")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    stem = title.replace(" ", "_")
    out_pdf = os.path.join(DATA_DIR, f"frequency_pattern_{stem}.pdf")
    out_png = os.path.join(DATA_DIR, f"frequency_pattern_{stem}.png")
    fig.savefig(out_pdf)
    fig.savefig(out_png, dpi=150)
    plt.close(fig)
    print(f"Saved: {out_pdf}")
