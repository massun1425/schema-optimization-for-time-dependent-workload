#!/usr/bin/env python3
"""ワークロードパターン別の図をまとめて再生成する統合スクリプト。

各パターンについて:
  1) per-timestep 実行時間（マイグレーション込み）の折れ線     -> {dir}/timestep_time_{freq}.pdf
  2) 総実行時間の積み上げ棒（クエリ実行 + マイグレーション）   -> {dir}/total_time_stacked_{freq}.pdf
最後に全パターンを1枚にまとめた積み上げ棒                       -> progress/scaling_pruning/total_time_stacked_all.pdf

手法色は全図で統一（Proposed=青 / Adapt=橙 / Static=緑）、マイグレーションは各色の薄色。
y は benchmark の total_time 生値（= migration.time + queries.total_time）。

使い方: .venv/bin/python progress/scaling_pruning/generate_figures.py
"""

import json
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.colors as mc
import matplotlib.pyplot as plt
import numpy as np

from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter


# (freq suffix, フォルダ)
PATTERNS = [
    ("24_2_10", "time_dependent_output/job-ceb-2/result_500M"),
    ("24_mono", "time_dependent_output/job-ceb-2/result_500M"),
    ("24_peak", "time_dependent_output/job-ceb-2/result_500M"),
    ("2h_x2_50x", "time_dependent_output/ex4/result_b500"),
]

# (凡例名, ファイル名のトークン, 色)
METHODS = [
    ("Adapt", "adaptive_w4", "#F58518"),
    ("Static", "static", "#54A24B"),
    ("Proposed", "dynamic", "#4C78A8"),
]


def lighten(hex_color, amt=0.6):
    """色を白側へ blend して薄くする（マイグレーション用）。"""
    c = mc.to_rgb(hex_color)
    return tuple(1 - (1 - x) * (1 - amt) for x in c)


def bench_path(D, tok, fq):
    return f"{D}/benchmark_results_{tok}_{fq}.json"


def format_hours(y, _):
    """秒を時間[h]に変換して表示する。"""
    return f"{y / 3600:.1f}"


def per_timestep(path):
    """各タイムステップの (index, total_time) を返す。total_time はマイグレーション込み。"""
    with open(path) as f:
        d = json.load(f)

    tr = d["timestep_results"]
    xs = [r.get("timestep_index", i) for i, r in enumerate(tr)]
    ys = [r["total_time"] for r in tr]

    return xs, ys


def split_total(path):
    """総 (クエリ実行時間, マイグレーション時間) をタイムステップ合計で返す。"""
    with open(path) as f:
        d = json.load(f)

    q = 0.0
    m = 0.0

    for r in d["timestep_results"]:
        q_i = (r.get("queries", {}) or {}).get("total_time", 0) or 0

        mig = r.get("migration") or {}
        m_i = (mig.get("time") or 0) if isinstance(mig, dict) else 0

        q += q_i
        m += m_i

    return q, m


def fig_timestep_line(fq, D):
    fig, ax = plt.subplots(figsize=(9, 5.2))

    for label, tok, color in METHODS:
        p = bench_path(D, tok, fq)

        if not os.path.exists(p):
            print("  MISSING", p)
            continue

        xs, ys = per_timestep(p)
        ax.plot(
            xs,
            ys,
            marker="o",
            markersize=4,
            linewidth=1.8,
            color=color,
            label=label,
        )

    ax.set_xlabel("Timestep")
    ax.set_ylabel("Execution time [h]")
    ax.yaxis.set_major_formatter(FuncFormatter(format_hours))

    ax.set_xticks(range(0, 24, 2))
    ax.legend()
    ax.grid(alpha=0.3)

    fig.tight_layout()

    out = f"{D}/timestep_time_{fq}.pdf"
    fig.savefig(out)
    plt.close(fig)

    print("saved", out)


def fig_total_stacked(fq, D):
    fig, ax = plt.subplots(figsize=(7, 5.5))

    labels = []
    values = []
    max_total = 0.0

    # 先に全手法の値を読み込んで最大値を計算
    for label, tok, color in METHODS:
        p = bench_path(D, tok, fq)
        labels.append(label)

        if not os.path.exists(p):
            print("  MISSING", p)
            values.append(None)
            continue

        q, m = split_total(p)
        values.append((q, m, color))

        max_total = max(max_total, q + m)

    # 描画
    for i, item in enumerate(values):
        if item is None:
            continue

        q, m, color = item

        ax.bar(i, q, color=color)
        ax.bar(i, m, bottom=q, color=lighten(color))

    ax.set_xticks(range(len(METHODS)))
    ax.set_xticklabels(labels)

    ax.set_ylabel("Total execution time [h]")
    ax.yaxis.set_major_formatter(FuncFormatter(format_hours))

    # 棒が上にはみ出したり詰まって見えたりしないように余白を明示
    if max_total > 0:
        ax.set_ylim(0, max_total * 1.15)

    ax.legend(
        handles=[
            Patch(facecolor="#555555", label="Query execution"),
            Patch(facecolor=lighten("#555555"), label="Migration"),
        ],
        loc="upper right",
    )

    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()

    out = f"{D}/total_time_stacked_{fq}.pdf"
    fig.savefig(out)
    plt.close(fig)

    print("saved", out)


def fig_total_stacked_all():
    x = np.arange(len(PATTERNS))
    w = 0.26

    fig, ax = plt.subplots(figsize=(11, 6))

    max_total = 0.0

    # 先に全データを読み込む
    all_values = {}

    for mi, (label, tok, color) in enumerate(METHODS):
        for pi, (fq, D) in enumerate(PATTERNS):
            p = bench_path(D, tok, fq)

            if not os.path.exists(p):
                print("  MISSING", p)
                continue

            q, m = split_total(p)
            all_values[(mi, pi)] = (q, m, color)

            max_total = max(max_total, q + m)

    # 描画
    for mi, (label, tok, color) in enumerate(METHODS):
        offset = (mi - 1) * w

        for pi, (fq, D) in enumerate(PATTERNS):
            item = all_values.get((mi, pi))

            if item is None:
                continue

            q, m, color = item

            ax.bar(pi + offset, q, w, color=color)
            ax.bar(pi + offset, m, w, bottom=q, color=lighten(color))

    ax.set_xticks(x)
    ax.set_xticklabels([fq for fq, _ in PATTERNS])

    ax.set_xlabel("Workload pattern")
    ax.set_ylabel("Total execution time [h]")
    ax.yaxis.set_major_formatter(FuncFormatter(format_hours))

    if max_total > 0:
        ax.set_ylim(0, max_total * 1.15)

    handles = [Patch(facecolor=c, label=l) for l, _, c in METHODS]
    handles.append(
        Patch(
            facecolor=lighten("#999999"),
            label="Migration",
        )
    )

    ax.legend(handles=handles, loc="upper left", fontsize=9)
    ax.grid(axis="y", alpha=0.3)

    fig.tight_layout()

    out = "progress/scaling_pruning/total_time_stacked_all.pdf"
    fig.savefig(out)
    plt.close(fig)

    print("saved", out)


def main():
    for fq, D in PATTERNS:
        print(f"[{fq}]")
        fig_timestep_line(fq, D)
        fig_total_stacked(fq, D)

    print("[combined]")
    fig_total_stacked_all()


if __name__ == "__main__":
    main()