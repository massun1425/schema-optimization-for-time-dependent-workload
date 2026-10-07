#!/usr/bin/env python3
"""RQ2: workload prediction recall vs. total execution time (Redbench synthetic).

Input:  time_dependent_output/rq2/
        benchmark_results_{dynamic,static}_2h_x2_50x{,_noise5,...,_noise50}.json
        benchmark_results_adaptive_w4_2h_x2_50x.json(constant: Adapt does not use predictions)
recall = 100 - noise (%). y-axis: summary.total_benchmark_time.
Output: rq2_prediction_recall.pdf
"""
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from common import COLORS, MARKERS, REDBENCH_SUFFIX, parse_args, require, save_pdf, total_benchmark_time

# recall increases from left to right (noise 0 = file without a noise suffix)
NOISES = [50, 45, 40, 35, 30, 25, 20, 15, 10, 5, 0]
METHODS = ["Adapt", "Static", "Proposed"]


def noise_suffix(n):
    return "" if n == 0 else f"_noise{n}"


def main():
    args = parse_args(__doc__)
    d = args.td_dir / "rq2"
    static_paths = [d / f"benchmark_results_static{REDBENCH_SUFFIX}{noise_suffix(n)}.json" for n in NOISES]
    dynamic_paths = [d / f"benchmark_results_dynamic{REDBENCH_SUFFIX}{noise_suffix(n)}.json" for n in NOISES]
    adapt_path = d / f"benchmark_results_adaptive_w4{REDBENCH_SUFFIX}.json"
    require(static_paths + dynamic_paths + [adapt_path])

    data = {
        "Static": [total_benchmark_time(p) for p in static_paths],
        "Proposed": [total_benchmark_time(p) for p in dynamic_paths],
        "Adapt": [total_benchmark_time(adapt_path)] * len(NOISES),
    }

    x = list(range(len(NOISES)))
    fig, ax = plt.subplots(figsize=(8, 5))
    for m in METHODS:
        ax.plot(x, data[m], marker=MARKERS[m], label=m, color=COLORS[m],
                linewidth=2, markersize=7)

    ax.set_xlabel("Workload Prediction Recall", fontsize=18)
    ax.set_ylabel("Total Execution Time (s)", fontsize=18)
    ax.set_title("Effect of Workload Prediction Recall", fontsize=20)
    ax.set_xticks(x)
    ax.set_xticklabels([f"{100 - n}%" for n in NOISES], fontsize=13)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.yaxis.set_minor_locator(ticker.MultipleLocator(20000))
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
    ax.legend(fontsize=14)
    ax.set_ylim(0, max(v for m in METHODS for v in data[m]) * 1.15)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    plt.tight_layout()
    save_pdf(fig, args.out_dir / "rq2_prediction_recall.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
