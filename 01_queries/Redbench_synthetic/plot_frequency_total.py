#!/usr/bin/env python3
"""Total execution-count over timesteps for the Redbench_synthetic frequency file.

Sums every query's execution count per timestep and draws a single line
(x = timestep, y = total execution count), following the reference plot style.
Targets frequency_time_dependent_2h_x2_50x.json. Output PDF (+PNG) into plots/.
"""
import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

FONT_SIZE = 16
plt.rcParams.update({
    "font.size": FONT_SIZE,
    "axes.titlesize": FONT_SIZE + 2,
    "axes.labelsize": FONT_SIZE,
    "xtick.labelsize": FONT_SIZE - 2,
    "ytick.labelsize": FONT_SIZE - 2,
})

DATA_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(DATA_DIR, "plots")
os.makedirs(OUTPUT_DIR, exist_ok=True)

FILENAME = "frequency_time_dependent_2h_x2_50x.json"
TITLE = "Redbench"

path = os.path.join(DATA_DIR, FILENAME)
data = json.load(open(path))
queries = data["queries"]

# 全クエリの実行回数をタイムステップごとに合計
n_steps = len(next(iter(queries.values())))
total = [sum(queries[k][t] for k in queries) for t in range(n_steps)]
timesteps = list(range(1, n_steps + 1))

fig, ax = plt.subplots(figsize=(10, 5))
ax.plot(timesteps, total, linewidth=1.8, color="steelblue")
ax.set_title(TITLE, fontsize=FONT_SIZE + 2)
ax.set_xlabel("Timestep")
ax.set_ylabel("Total execution count")
ax.grid(True, alpha=0.3)
fig.tight_layout()

out_pdf = os.path.join(OUTPUT_DIR, f"frequency_pattern_{TITLE.replace(' ', '_')}.pdf")
out_png = os.path.join(OUTPUT_DIR, f"frequency_pattern_{TITLE.replace(' ', '_')}.png")
fig.savefig(out_pdf)
fig.savefig(out_png, dpi=150)
plt.close(fig)
print(f"Saved: {out_pdf}")
