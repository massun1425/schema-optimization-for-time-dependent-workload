#!/usr/bin/env python3
"""Table 2: 候補プルーニングの有無による比較（LaTeX と Markdown）.

入力: time_dependent_output/rq3/
        td_mv_optimization_result_{fq}{,_wo}.json, benchmark_results_dynamic_{fq}{,_wo}.json
        （'' = with pruning, '_wo' = without pruning）
列:
  候補数          : without = pruning_info.total_candidates（with 側の値）/ with = promising_candidates
  最適化時間 (s)  : pruning_time_sec + solve_time_sec（without は solve_time_sec のみ）
  総実行時間 (s)  : summary.total_benchmark_time（各パターンで小さい方を太字）
  目的関数値      : -objective / 1000
出力: rq3_pruning.tex, rq3_pruning.md
"""
from common import PATTERNS, load_json, parse_args, require, total_benchmark_time

# (行ラベル, ファイルのタグ)
VARIANTS = [("Without pruning", "_wo"), ("With pruning", "")]


def main():
    args = parse_args(__doc__)
    src = args.td_dir / "rq3"

    def td_path(sfx, tag):
        return src / f"td_mv_optimization_result{sfx}{tag}.json"

    def bm_path(sfx, tag):
        return src / f"benchmark_results_dynamic{sfx}{tag}.json"

    require([f(sfx, tag) for sfx, _ in PATTERNS for _, tag in VARIANTS for f in (td_path, bm_path)])

    rows = {}
    for sfx, pname in PATTERNS:
        total = load_json(td_path(sfx, ""))["pruning_info"]["total_candidates"]
        for vlabel, tag in VARIANTS:
            td = load_json(td_path(sfx, tag))
            rows[(pname, vlabel)] = {
                "n_cand": td["pruning_info"]["promising_candidates"] if tag == "" else total,
                "opt_time": td.get("pruning_time_sec", 0.0) + td["solve_time_sec"],
                "total_exec": total_benchmark_time(bm_path(sfx, tag)),
                "obj_k": -td["objective"] / 1000.0,
            }

    best = {}
    for _, pname in PATTERNS:
        a = rows[(pname, "Without pruning")]["total_exec"]
        b = rows[(pname, "With pruning")]["total_exec"]
        best[pname] = "Without pruning" if a <= b else "With pruning"

    # ---------------- LaTeX（桁区切りなし）----------------
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Comparison of optimization time, total execution time, "
        r"and objective value for each workload pattern, with and without "
        r"candidate pruning.}",
        r"\label{table:ex3_1}",
        r"\begin{tabular}{llrrrr}",
        r"\toprule",
        r"Workload pattern & Candidate pruning & "
        r"\shortstack{Number of candidates\\before whole-time-step opt.} & "
        r"\shortstack{Optimization\\time (s)} & "
        r"\shortstack{Total execution\\time (s)} & "
        r"Objective value ($\times 10^{3}$) \\",
        r"\midrule",
    ]
    for pi, (_, pname) in enumerate(PATTERNS):
        for vi, (vlabel, _) in enumerate(VARIANTS):
            r = rows[(pname, vlabel)]
            first = r"\multirow{2}{*}{" + pname + "}" if vi == 0 else ""
            exec_s = f"{r['total_exec']:.0f}"
            if best[pname] == vlabel:
                exec_s = rf"\textbf{{{exec_s}}}"
            lines.append(f"{first} & {vlabel} & {r['n_cand']:.0f} & {r['opt_time']:.1f} & "
                         f"{exec_s} & {r['obj_k']:.0f} \\\\")
            if vi == 0:
                lines.append(r"\cmidrule(l){2-6}")
        if pi < len(PATTERNS) - 1:
            lines.append(r"\midrule")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table*}"]
    tex_path = args.out_dir / "rq3_pruning.tex"
    tex_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"saved: {tex_path}")

    # ---------------- Markdown（表のみ, 桁区切りあり）----------------
    md = [
        "| Workload pattern | Candidate pruning | # candidates before whole-time-step opt. "
        "| Optimization time (s) | Total execution time (s) | Objective value (×10³) |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for _, pname in PATTERNS:
        for vlabel, _ in VARIANTS:
            r = rows[(pname, vlabel)]
            exec_s = f"{r['total_exec']:,.0f}"
            if best[pname] == vlabel:
                exec_s = f"**{exec_s}**"
            pcell = pname if vlabel == "Without pruning" else ""
            md.append(f"| {pcell} | {vlabel} | {r['n_cand']:,.0f} | {r['opt_time']:.1f} | "
                      f"{exec_s} | {r['obj_k']:,.0f} |")
    md_path = args.out_dir / "rq3_pruning.md"
    md_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"saved: {md_path}")


if __name__ == "__main__":
    main()
