#!/usr/bin/env python3
"""Fig.8: 最適化時間 vs タイムステップ数（プルーニング有無）.

入力: time_dependent_output/rq1/exp1_2/td_mv_optimization_result_{T}_mono_{wp,wo}.json
縦軸: phase_time_sec（Phase 6 全体の実時間。wp = プルーニング + ILP 求解, wo = ILP 求解）
出力: rq1_exp1_2_timestep_scaling.pdf
"""
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np

from common import COLORS, load_json, parse_args, require, save_pdf

TIMESTEPS = [12, 18, 24, 30, 36, 42]
# (凡例, ファイル名のタグ) — 並び順 = 棒の順
SERIES = [("Proposed (w/ pruning)", "wp"), ("Proposed (w/o pruning)", "wo")]


def main():
    args = parse_args(__doc__)
    src = args.td_dir / "rq1" / "exp1_2"
    paths = {(ts, tag): src / f"td_mv_optimization_result_{ts}_mono_{tag}.json"
             for ts in TIMESTEPS for _, tag in SERIES}
    require(paths.values())

    values = np.array([[load_json(paths[(ts, tag)])["phase_time_sec"] for _, tag in SERIES]
                       for ts in TIMESTEPS])

    x = np.arange(len(TIMESTEPS))
    n = len(SERIES)
    width = 0.32
    offsets = np.linspace(-(n - 1) / 2, (n - 1) / 2, n) * width

    fig, ax = plt.subplots(figsize=(14, 8.09))
    for i, (label, _) in enumerate(SERIES):
        ax.bar(x + offsets[i], values[:, i], width, label=label, color=COLORS[label])

    ax.set_xlabel("Number of Timesteps", fontsize=22)
    ax.set_ylabel("Optimization Time (s)", fontsize=22)
    ax.set_xticks(x)
    ax.set_xticklabels([str(ts) for ts in TIMESTEPS], fontsize=20)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.tick_params(axis="y", labelsize=18)
    ax.legend(fontsize=18)
    ax.set_ylim(0, values.max() * 1.10)
    ax.yaxis.set_major_locator(ticker.MultipleLocator(500))
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)

    plt.tight_layout()
    save_pdf(fig, args.out_dir / "rq1_exp1_2_timestep_scaling.pdf")
    plt.close(fig)


if __name__ == "__main__":
    main()
