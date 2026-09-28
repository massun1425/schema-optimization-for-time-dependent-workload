"""Shared settings and helpers for the paper figure/table scripts.

Inputs are the results of paper/*.sh (time_dependent_output/rq*/) and, for the
frequency-pattern figures only, the frequency files in 01_queries/. Outputs are PDFs
(the table is written as .tex and .md).
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

REPO_ROOT = Path(__file__).resolve().parent.parent

# Colors and markers per method (shared by all figures)
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

# Frequency patterns of job-ceb-2: (frequency suffix, name in the paper)
PATTERNS = [
    ("_24_2_10", "Cycles"),
    ("_24_mono", "Evolution and Stagnation"),
    ("_24_peak", "Growth and Spikes"),
]
REDBENCH_SUFFIX = "_2h_x2_50x"


def parse_args(description):
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--td-dir", type=Path, default=REPO_ROOT / "time_dependent_output",
                    help="output directory of paper/*.sh (contains rq1/ rq2/ ...)")
    ap.add_argument("--queries-dir", type=Path, default=REPO_ROOT / "01_queries",
                    help="directory with the frequency files (used only for Fig. 5 / Fig. 6)")
    ap.add_argument("--out-dir", type=Path, default=REPO_ROOT / "paper_figures" / "output",
                    help="output directory for the figures and tables")
    args = ap.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    return args


def require(paths):
    """Check that all input files exist; otherwise list the missing ones and exit."""
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print("Input files not found (run the corresponding script in paper/ first):",
              file=sys.stderr)
        for p in missing:
            print(f"  {p}", file=sys.stderr)
        sys.exit(1)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def total_benchmark_time(path):
    """Total execution time = query execution + migration (Static includes the initial MV build)."""
    return load_json(path)["summary"]["total_benchmark_time"]


def save_pdf(fig, path, **kwargs):
    # Do not embed CreationDate (so that the same input always yields the same PDF)
    fig.savefig(path, metadata={"CreationDate": None}, **kwargs)
    print(f"saved: {path}")
