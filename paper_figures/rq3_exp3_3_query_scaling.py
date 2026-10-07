#!/usr/bin/env python3
"""RQ3 Exp3-3: optimization time vs. number of queries (Static / with / without pruning).

Input:  time_dependent_output/rq3/exp3_3/job-ceb-2-q{N}/
        static_mv_optimization_result_24_mono.json     （Static: execution_time）
        td_mv_optimization_result_24_mono_wp.json      （w/ pruning: phase_time_sec）
        td_mv_optimization_result_24_mono_wo.json      （w/o pruning: phase_time_sec）
        DNF_24_mono_wo.txt                              (marker: w/o pruning did not finish within 24h)
      A size without a w/o-pruning result but with a DNF marker is drawn as a hatched bar up to 24h labeled "DNF".
y-axis: time (hours, 0-24)
Output: rq3_exp3_3_query_scaling.pdf
"""
import sys

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

from common import COLORS, load_json, parse_args, require, save_pdf

NS = [20000, 40000, 60000, 80000, 100000]
HOUR = 3600.0
Y_MAX = 24  # hours
SFX = "_24_mono"
SERIES = ["Static", "Proposed (w/ pruning)", "Proposed (w/o pruning)"]


def main():
    args = parse_args(__doc__)
    base = args.td_dir / "rq3" / "exp3_3"

    static_paths = [base / f"job-ceb-2-q{n}" / f"static_mv_optimization_result{SFX}.json" for n in NS]
    wp_paths = [base / f"job-ceb-2-q{n}" / f"td_mv_optimization_result{SFX}_wp.json" for n in NS]
    require(static_paths + wp_paths)

    static_h = [load_json(p)["execution_time"] / HOUR for p in static_paths]
    wp_h = [load_json(p)["phase_time_sec"] / HOUR for p in wp_paths]

    # w/o pruning: result -> value, DNF marker -> None (DNF), neither -> error (not run)
    wo_h, not_run = [], []
    for n in NS:
        d = base / f"job-ceb-2-q{n}"
        res, dnf = d / f"td_mv_optimization_result{SFX}_wo.json", d / f"DNF{SFX}_wo.txt"
        if res.exists():
            wo_h.append(load_json(res)["phase_time_sec"] / HOUR)
        elif dnf.exists():
            wo_h.append(None)
        else:
            not_run.append(res)
    if not_run:
        print("Neither a w/o-pruning result nor a DNF marker exists (not run):", file=sys.stderr)
        for p in not_run:
            print(f"  {p}", file=sys.stderr)
        sys.exit(1)

    x = np.arange(len(NS))
    w = 0.26
    fig, ax = plt.subplots(figsize=(9, 5.5))
    for name, ys, off in [(SERIES[0], static_h, -w), (SERIES[1], wp_h, 0.0), (SERIES[2], wo_h, w)]:
        for i, y in enumerate(ys):
            xi = x[i] + off
            if y is None:
                ax.bar(xi, Y_MAX, w, color=COLORS[name], alpha=0.30,
                       hatch="///", edgecolor=COLORS[name], linewidth=1.0)
                ax.text(xi, Y_MAX * 0.55, "DNF", ha="center", va="center",
                        rotation=90, fontsize=10, fontweight="bold", color=COLORS[name])
            else:
                ax.bar(xi, y, w, color=COLORS[name])

    ax.set_xticks(x)
    ax.set_xticklabels([f"{n // 1000}k" for n in NS], fontsize=13)
    ax.set_xlabel("Number of queries", fontsize=16)
    ax.set_ylabel("Optimization time (hours)", fontsize=16)
    ax.set_ylim(0, Y_MAX)
    ax.set_yticks(range(0, Y_MAX + 1, 4))
    ax.axhline(Y_MAX, color="gray", linestyle=":", linewidth=1.0)
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(handles=[mpatches.Patch(color=COLORS[n], label=n) for n in SERIES],
              fontsize=12, loc="upper left")

    fig.tight_layout()
    save_pdf(fig, args.out_dir / "rq3_exp3_3_query_scaling.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
