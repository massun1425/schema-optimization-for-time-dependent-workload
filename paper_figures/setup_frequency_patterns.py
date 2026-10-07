#!/usr/bin/env python3
"""Workload setup: frequency patterns (Cycles / Evolution and Stagnation / Growth and Spikes).

Input:  01_queries/job-ceb-2/frequency_time_dependent_{24_2_10,24_mono,24_peak}.json
        Group A = first odd-numbered query (e.g. 1a.sql), Group B = first even-numbered query (e.g. 2a.sql)
Output: setup_frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf
"""
import re

import matplotlib.lines as mlines
import matplotlib.pyplot as plt

from common import PATTERNS, load_json, parse_args, require, save_pdf

COLOR_A = "tab:blue"
COLOR_B = "tab:red"
FONT_SIZE = 20


def query_number(key):
    return int(re.match(r"(\d+)", key).group(1))


def main():
    args = parse_args(__doc__)
    paths = {title: args.queries_dir / "job-ceb-2" / f"frequency_time_dependent{sfx}.json"
             for sfx, title in PATTERNS}
    require(paths.values())

    plt.rcParams.update({
        "font.size": FONT_SIZE,
        "axes.titlesize": FONT_SIZE + 2,
        "axes.labelsize": FONT_SIZE,
        "xtick.labelsize": FONT_SIZE - 2,
        "ytick.labelsize": FONT_SIZE - 2,
        "legend.fontsize": FONT_SIZE - 2,
    })

    for title, path in paths.items():
        queries = load_json(path)["queries"]

        fig, ax = plt.subplots(figsize=(12, 5))
        fig.suptitle(title, fontsize=FONT_SIZE + 2)

        for parity, color in [(1, COLOR_A), (0, COLOR_B)]:
            keys = sorted(
                [k for k in queries if re.match(r"(\d+)", k) and query_number(k) % 2 == parity],
                key=query_number,
            )
            freqs = queries[keys[0]]
            ax.plot(range(1, len(freqs) + 1), freqs, color=color, linewidth=2.0)

        legend_handles = [
            mlines.Line2D([], [], color=COLOR_A, linewidth=2.5, label="Group A "),
            mlines.Line2D([], [], color=COLOR_B, linewidth=2.5, label="Group B "),
        ]
        ax.legend(handles=legend_handles, loc="upper left")
        ax.set_xlabel("Timestep")
        ax.set_ylabel("Execution count")
        ax.grid(True, alpha=0.3)

        fig.tight_layout()
        save_pdf(fig, args.out_dir / f"setup_frequency_pattern_{title.replace(' ', '_')}.pdf")
        plt.close(fig)


if __name__ == "__main__":
    main()
