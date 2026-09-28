#!/usr/bin/env python3
"""Fig. 6: total execution count per time step of Redbench synthetic.

Input:  01_queries/Redbench_synthetic/frequency_time_dependent_2h_x2_50x.json
Output: setup_redbench_total_count.pdf
"""
import matplotlib.pyplot as plt

from common import REDBENCH_SUFFIX, load_json, parse_args, require, save_pdf

FONT_SIZE = 16


def main():
    args = parse_args(__doc__)
    path = args.queries_dir / "Redbench_synthetic" / f"frequency_time_dependent{REDBENCH_SUFFIX}.json"
    require([path])

    plt.rcParams.update({
        "font.size": FONT_SIZE,
        "axes.titlesize": FONT_SIZE + 2,
        "axes.labelsize": FONT_SIZE,
        "xtick.labelsize": FONT_SIZE - 2,
        "ytick.labelsize": FONT_SIZE - 2,
    })

    queries = load_json(path)["queries"]
    n_steps = len(next(iter(queries.values())))
    total = [sum(queries[k][t] for k in queries) for t in range(n_steps)]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(range(1, n_steps + 1), total, linewidth=1.8, color="steelblue")
    ax.set_title("Redbench", fontsize=FONT_SIZE + 2)
    ax.set_xlabel("Timestep")
    ax.set_ylabel("Total execution count")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    save_pdf(fig, args.out_dir / "setup_redbench_total_count.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
