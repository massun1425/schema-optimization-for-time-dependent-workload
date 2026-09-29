#!/usr/bin/env python3
"""Generate Table 3 (pruning comparison) as LaTeX + a GFM markdown table.

Reads from time_dependent_output/ex3_500M_ok/:
  td_mv_optimization_result_{fq}{tag}.json         (optimization)
  benchmark_results_dynamic_{fq}{tag}.json          (execution)
  tag: '' = with pruning, '_wo' = without pruning.

Column definitions (confirmed):
  # candidates before whole-time-step opt.
      without pruning : total candidate count (== pruning_info.total_candidates)
      with pruning    : pruning_info.promising_candidates
  Optimization time (s) = pruning_time_sec + solve_time_sec
      (without pruning has no pruning_time -> solve_time only)
  Total execution time (s) = benchmark summary.total_benchmark_time
  Objective value (x10^3) = -objective / 1000   (objective is negative)

Bold marks the better (lower) total execution time within each pattern.
"""
import json
from pathlib import Path

SRC = Path("time_dependent_output/ex3_500M_ok")
OUT = Path("progress/ex3_500M")

# display name -> frequency suffix
PATTERNS = [
    ("Cycles", "24_2_10"),
    ("Evolution and Stagnation", "24_mono"),
    ("Growth and Spikes", "24_peak"),
]
# (row label, file tag)
VARIANTS = [("Without pruning", "_wo"), ("With pruning", "")]

TOTAL_CANDIDATES = None  # sanity: same across all (== 26312)


def total_candidates(fq):
    """Full candidate count lives only in the with-pruning file's pruning_info."""
    td = json.load(open(SRC / f"td_mv_optimization_result_{fq}.json"))
    return td["pruning_info"]["total_candidates"]


def load(fq, tag):
    td = json.load(open(SRC / f"td_mv_optimization_result_{fq}{tag}.json"))
    bm = json.load(open(SRC / f"benchmark_results_dynamic_{fq}{tag}.json"))
    pi = td.get("pruning_info", {})
    total = total_candidates(fq)
    if tag == "":  # with pruning
        n_cand = pi.get("promising_candidates")
    else:          # without pruning -> full candidate set
        n_cand = total
    opt_time = td.get("pruning_time_sec", 0.0) + td["solve_time_sec"]
    total_exec = bm["summary"]["total_benchmark_time"]
    obj_k = -td["objective"] / 1000.0
    return {
        "n_cand": n_cand,
        "total_full": total,
        "opt_time": opt_time,
        "total_exec": total_exec,
        "obj_k": obj_k,
    }


# collect
rows = {}  # (pattern, variant_label) -> dict
for pname, fq in PATTERNS:
    for vlabel, tag in VARIANTS:
        rows[(pname, vlabel)] = load(fq, tag)

# which variant has the lower total execution time per pattern (for bolding)
best_exec = {}
for pname, _ in PATTERNS:
    a = rows[(pname, "Without pruning")]["total_exec"]
    b = rows[(pname, "With pruning")]["total_exec"]
    best_exec[pname] = "Without pruning" if a <= b else "With pruning"


def fnum(x):
    # LaTeX: match the reference image (integers, no thousands separators)
    return f"{x:.0f}"


def fmd(x):
    # markdown: comma separators for readability
    return f"{x:,.0f}"


# ---------------- LaTeX ----------------
def latex_cell_exec(pname, vlabel, val):
    s = fnum(val)
    return rf"\textbf{{{s}}}" if best_exec[pname] == vlabel else s


lines = []
lines.append(r"\begin{table*}[t]")
lines.append(r"\centering")
lines.append(r"\caption{Comparison of optimization time, total execution time, "
             r"and objective value for each workload pattern, with and without "
             r"candidate pruning.}")
lines.append(r"\label{table:ex3_1}")
lines.append(r"\begin{tabular}{llrrrr}")
lines.append(r"\toprule")
lines.append(r"Workload pattern & Candidate pruning & "
             r"\shortstack{Number of candidates\\before whole-time-step opt.} & "
             r"\shortstack{Optimization\\time (s)} & "
             r"\shortstack{Total execution\\time (s)} & "
             r"Objective value ($\times 10^{3}$) \\")
lines.append(r"\midrule")

for pi, (pname, fq) in enumerate(PATTERNS):
    for vi, (vlabel, tag) in enumerate(VARIANTS):
        r = rows[(pname, vlabel)]
        first = r"\multirow{2}{*}{" + pname + "}" if vi == 0 else ""
        lines.append(
            f"{first} & {vlabel} & {fnum(r['n_cand'])} & "
            f"{r['opt_time']:.1f} & "
            f"{latex_cell_exec(pname, vlabel, r['total_exec'])} & "
            f"{fnum(r['obj_k'])} \\\\"
        )
        if vi == 0:
            lines.append(r"\cmidrule(l){2-6}")
    if pi < len(PATTERNS) - 1:
        lines.append(r"\midrule")

lines.append(r"\bottomrule")
lines.append(r"\end{tabular}")
lines.append(r"\end{table*}")

tex = "\n".join(lines) + "\n"
(OUT / "table3.tex").write_text(tex, encoding="utf-8")
print("wrote", OUT / "table3.tex")

# ---------------- Markdown (GFM) ----------------
md = []
md.append("| Workload pattern | Candidate pruning | # candidates before whole-time-step opt. | Optimization time (s) | Total execution time (s) | Objective value (×10³) |")
md.append("|---|---|---:|---:|---:|---:|")
for pname, fq in PATTERNS:
    for vlabel, tag in VARIANTS:
        r = rows[(pname, vlabel)]
        exec_s = fmd(r["total_exec"])
        if best_exec[pname] == vlabel:
            exec_s = f"**{exec_s}**"
        pcell = pname if vlabel == "Without pruning" else ""
        md.append(f"| {pcell} | {vlabel} | {fmd(r['n_cand'])} | {r['opt_time']:.1f} | {exec_s} | {fmd(r['obj_k'])} |")
md_table = "\n".join(md)
(OUT / "table3_markdown.md").write_text(md_table + "\n", encoding="utf-8")
print("wrote", OUT / "table3_markdown.md")

# stdout preview
print("\n" + md_table)
