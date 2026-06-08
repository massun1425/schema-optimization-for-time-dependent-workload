"""
ベンチマーク結果の折れ線グラフ描画ユーティリティ

各タイムステップにおけるクエリ実行時間＋マイグレーション時間の和を折れ線グラフで描画する。

直接実行:
    python utils/plot_benchmark.py              # 画面表示
    python utils/plot_benchmark.py out.png      # ファイル保存

ファイルリストは下部の FILES セクションを編集する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

import matplotlib.pyplot as plt


def _load_series(path: str | Path) -> tuple[list[int], list[float], list[float]]:
    """JSONから (timestep_indices, query_times, migration_times) を返す。"""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    timestep_indices: list[int] = []
    query_times: list[float] = []
    migration_times: list[float] = []

    for ts in data.get("timestep_results", []):
        idx = ts.get("timestep_index", ts.get("timestep", len(timestep_indices)))
        timestep_indices.append(int(idx))

        queries = ts.get("queries", {})
        q_time = float(queries.get("total_time", 0.0)) if isinstance(queries, dict) else 0.0

        mig = ts.get("migration")
        if isinstance(mig, dict) and mig.get("success"):
            m_time = float(mig.get("time", 0.0))
        else:
            m_time = 0.0

        query_times.append(q_time)
        migration_times.append(m_time)

    return timestep_indices, query_times, migration_times


def plot_benchmark_lines(
    files: Sequence[tuple[str | Path, str]],
    *,
    title: str = "Benchmark: Query + Migration Time per Timestep",
    xlabel: str = "Timestep",
    ylabel: str = "Time (s)",
    figsize: tuple[float, float] = (10, 5),
    save_path: str | Path | None = None,
    show: bool = True,
) -> plt.Figure:
    """
    複数の結果ファイルを折れ線グラフで描画する。

    Args:
        files:     [(ファイルパス, ラベル), ...] のリスト。
                   パスはプロジェクトルートからの相対パスまたは絶対パス。
        title:     グラフタイトル。
        xlabel:    X軸ラベル。
        ylabel:    Y軸ラベル。
        figsize:   図サイズ (width, height) インチ。
        save_path: 指定した場合、そのパスに画像を保存する。
        show:      True の場合 plt.show() を呼ぶ。

    Returns:
        matplotlib Figure オブジェクト。
    """
    fig, ax = plt.subplots(figsize=figsize)

    for path, label in files:
        try:
            indices, q_times, m_times = _load_series(path)
        except FileNotFoundError:
            print(f"[警告] ファイルが見つかりません: {path}")
            continue
        except (KeyError, json.JSONDecodeError) as e:
            print(f"[警告] 読み込みエラー ({path}): {e}")
            continue

        total = [q + m for q, m in zip(q_times, m_times)]
        ax.plot(indices, total, marker="o", label=label)

    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.legend(loc="best")
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()

    if save_path is not None:
        fig.savefig(save_path, dpi=150)
        print(f"保存: {save_path}")

    if show:
        plt.show()

    return fig


# ==============================================================================
# ここを編集して使用する結果ファイルを指定する
# (ファイルパス, グラフ上のラベル)
# ==============================================================================
FILES = [
    ("time_dependent_output/job/result_100M_edbt/benchmark_results_dynamic_16_2_10.json", "Dynamic"),
    ("time_dependent_output/job/result_100M_edbt/benchmark_results_static_16_2_10.json",  "Static"),
    ("time_dependent_output/job/result_100M_edbt/benchmark_results_adaptive_w4_16_2_10.json", "Adap"),
]

TITLE     = "Benchmark: Query + Migration Time per Timestep"
SAVE_PATH = None  # 例: "result.png"  None の場合は画面表示のみ
# ==============================================================================


if __name__ == "__main__":
    import sys

    save = sys.argv[1] if len(sys.argv) > 1 else SAVE_PATH
    plot_benchmark_lines(FILES, title=TITLE, save_path=save, show=(save is None))
