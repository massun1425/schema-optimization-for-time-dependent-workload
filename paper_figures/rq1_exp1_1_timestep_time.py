#!/usr/bin/env python3
"""Fig.7: 各時刻の実行時間（Proposed / Adapt / Static）.

入力: time_dependent_output/rq1/exp1_1/{job-ceb-2,Redbench_synthetic}/
      benchmark_results_{dynamic,adaptive_w4,static}{suffix}.json
縦軸: timestep_results[t].total_time（= マイグレーション + クエリ実行）。
      Static は一度だけの初期 MV 構築時間（initial_mv_creation_time）を t=1 に加算する。
出力: rq1_exp1_1_timestep_time_{cycles,evolution_and_stagnation,growth_and_spikes,redbench_synthetic}.pdf
"""
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

from common import (COLORS, MARKERS, PATTERNS, REDBENCH_SUFFIX, load_json, parse_args,
                    require, save_pdf)

# (凡例, ファイル名の手法トークン, 初期 MV 構築を t=1 に加算するか)
METHODS = [
    ("Proposed", "dynamic", False),
    ("Adapt", "adaptive_w4", False),
    ("Static", "static", True),
]


def per_timestep_total(path, add_initial_mv):
    d = load_json(path)
    tr = d["timestep_results"]
    xs = [r.get("timestep_index", i) + 1 for i, r in enumerate(tr)]  # 1 始まり
    ys = [r["total_time"] for r in tr]
    if add_initial_mv and ys:
        ys[0] += d.get("initial_mv_creation_time", 0.0) or 0.0
    return xs, ys


def plot_panel(title, paths, out_path):
    fig, ax = plt.subplots(figsize=(9, 5.2))
    for label, _tok, add_init in METHODS:
        xs, ys = per_timestep_total(paths[label], add_init)
        ax.plot(xs, ys, marker=MARKERS[label], markersize=6, linewidth=2,
                color=COLORS[label], label=label)

    ax.set_xlabel("Timestep", fontsize=18)
    ax.set_ylabel("Execution Time (s)", fontsize=18)
    ax.set_title(title, fontsize=20)
    ax.set_xticks(range(1, 25, 2))
    ax.tick_params(labelsize=13)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_axisbelow(True)
    ax.grid(axis="y", linestyle="--", linewidth=0.6, alpha=0.4)
    ax.legend(fontsize=14)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    save_pdf(fig, out_path)
    plt.close(fig)


def main():
    args = parse_args(__doc__)
    base = args.td_dir / "rq1" / "exp1_1"

    # (タイトル, クエリセット, 頻度サフィックス)
    panels = [(title, "job-ceb-2", sfx) for sfx, title in PATTERNS]
    panels.append(("Redbench synthetic", "Redbench_synthetic", REDBENCH_SUFFIX))

    jobs = []
    for title, qset, sfx in panels:
        paths = {label: base / qset / f"benchmark_results_{tok}{sfx}.json"
                 for label, tok, _ in METHODS}
        jobs.append((title, paths))
    require([p for _, paths in jobs for p in paths.values()])

    for title, paths in jobs:
        stem = title.lower().replace(" ", "_")
        plot_panel(title, paths, args.out_dir / f"rq1_exp1_1_timestep_time_{stem}.pdf")


if __name__ == "__main__":
    main()
