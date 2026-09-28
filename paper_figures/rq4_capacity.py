#!/usr/bin/env python3
"""Fig.11: ストレージ制約と総実行時間（3 パターンを横に並べた 1 枚の図）.

入力: time_dependent_output/rq4/{24_2_10,24_mono,24_peak}/b{500,1000,1500,2000}/
        benchmark_results_{adaptive_w4,static,dynamic}_{suffix}.json
縦軸: summary.total_benchmark_time（Static は初期 MV 構築を含む）。k 表記、各パネルで下限を調整。
出力: rq4_capacity.pdf
"""
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from common import COLORS, PATTERNS, parse_args, require, save_pdf, total_benchmark_time

CAPS = [500, 1000, 1500, 2000]
METHODS = ["Adapt", "Static", "Proposed"]
TOKENS = {"Adapt": "adaptive_w4", "Static": "static", "Proposed": "dynamic"}


def main():
    args = parse_args(__doc__)
    base = args.td_dir / "rq4"

    def path(sfx, cap, m):
        return base / sfx.lstrip("_") / f"b{cap}" / f"benchmark_results_{TOKENS[m]}{sfx}.json"

    require([path(sfx, cap, m) for sfx, _ in PATTERNS for cap in CAPS for m in METHODS])

    fig, axes = plt.subplots(1, 3, figsize=(20, 6.5))
    bar_handles = None
    for ax, (sfx, title) in zip(axes, PATTERNS):
        values = np.array([[total_benchmark_time(path(sfx, cap, m)) for m in METHODS]
                           for cap in CAPS])
        x = np.arange(len(CAPS))
        n = len(METHODS)
        width = 0.24
        offsets = np.linspace(-(n - 1) / 2, (n - 1) / 2, n) * width

        hs = [ax.bar(x + offsets[i], values[:, i], width, label=m, color=COLORS[m])
              for i, m in enumerate(METHODS)]
        if bar_handles is None:
            bar_handles = hs

        ax.set_title(title, fontsize=24)
        ax.set_xlabel("Capacity (MB)", fontsize=22)
        ax.set_xticks(x)
        ax.set_xticklabels([str(c) for c in CAPS], fontsize=19)
        dmin, dmax = values.min(), values.max()
        rng = dmax - dmin
        ax.set_ylim(max(0, dmin - 0.12 * rng), dmax + 0.08 * rng)
        ax.yaxis.set_major_locator(ticker.MaxNLocator(6))
        ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v/1000:.0f}k"))
        ax.tick_params(axis="y", labelsize=18)
        ax.set_axisbelow(True)
        ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
        ax.tick_params(axis="x", which="both", bottom=False, top=False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    axes[0].set_ylabel("Total Execution Time (s)", fontsize=22)
    fig.legend([h[0] for h in bar_handles], METHODS, loc="upper center", ncol=3,
               fontsize=22, frameon=True, bbox_to_anchor=(0.5, 1.06))
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    save_pdf(fig, args.out_dir / "rq4_capacity.pdf", bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
