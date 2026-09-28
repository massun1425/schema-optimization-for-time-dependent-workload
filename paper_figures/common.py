"""論文図表スクリプトの共通設定・関数.

入力は paper/*.sh の実行結果（time_dependent_output/rq*/）と、
頻度パターン図のみ 01_queries/ の頻度ファイル。出力は PDF（表は .tex と .md）。
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

REPO_ROOT = Path(__file__).resolve().parent.parent

# 手法ごとの配色・マーカー（全図で統一）
COLORS = {
    "Adapt": "#4272A8",
    "Static": "#7E9E8E",
    "Proposed": "#A84040",
    "Proposed (w/ pruning)": "#A84040",
    "Proposed (w/o pruning)": "#DD8452",
}
MARKERS = {
    "Adapt": "o",
    "Static": "s",
    "Proposed": "^",
}

# job-ceb-2 の頻度パターン: (頻度サフィックス, 論文での名称)
PATTERNS = [
    ("_24_2_10", "Cycles"),
    ("_24_mono", "Evolution and Stagnation"),
    ("_24_peak", "Growth and Spikes"),
]
REDBENCH_SUFFIX = "_2h_x2_50x"


def parse_args(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--td-dir", type=Path, default=REPO_ROOT / "time_dependent_output",
                    help="paper/*.sh の出力先（rq1/ rq2/ ... を含むディレクトリ）")
    ap.add_argument("--queries-dir", type=Path, default=REPO_ROOT / "01_queries",
                    help="頻度ファイルのあるディレクトリ（Fig.5 / Fig.6 のみ使用）")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "paper_figures" / "output",
                    help="図表の出力先")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    return args


def require(paths):
    """入力ファイルがすべて揃っているか確認し、足りなければ一覧を出して終了する."""
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print("入力ファイルが見つかりません（paper/ の該当スクリプトを先に実行してください）:",
              file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        sys.exit(1)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def total_benchmark_time(path):
    """総実行時間 = クエリ実行 + マイグレーション（Static は初期 MV 構築を含む）."""
    return load_json(path)["summary"]["total_benchmark_time"]


def save_pdf(fig, path, **kwargs):
    # CreationDate を埋め込まない（同じ入力から同じ PDF を得るため）
    fig.savefig(path, metadata={"CreationDate": None}, **kwargs)
    print(f"saved: {path}")
