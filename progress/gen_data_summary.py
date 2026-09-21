#!/usr/bin/env python3
"""Collect the numeric evidence used in the experiment discussions into one
markdown file (minimal prose, numbers preserved)."""
import json
import os

OUT = "progress/2026-08-09_experiment_data_summary.md"
H = 3600.0
L = []
def w(s=""): L.append(s)


def bt(path):
    return json.load(open(path))["summary"]["total_benchmark_time"]


def series_total(path):
    d = json.load(open(path))
    return [r["total_time"] for r in d["timestep_results"]]


w("# 実験データ要約（考察の論拠数値）")
w()
w("作成日: 2026-08-09  ／ 各考察で用いた数値をまとめたもの（本文は最小限）。")
w()

# ---------------------------------------------------------------- ex1_1
w("## 1. タイムステップ別実行時間 (ex1_1)")
w()
w("縦軸 = 各時刻の `total_time`（クエリ実行 + マイグレーション）を24時刻合計。")
w("データ: result_500M_ok (24_2_10/mono/peak) + ex2_500M_ok (2h_x2_50x)。")
w()
ex1 = {
    "Cycles": ("time_dependent_output/job-ceb-2/result_500M_ok", "24_2_10"),
    "Evolution and Stagnation": ("time_dependent_output/job-ceb-2/result_500M_ok", "24_mono"),
    "Growth and Spikes": ("time_dependent_output/job-ceb-2/result_500M_ok", "24_peak"),
    "Redbench synthetic": ("time_dependent_output/ex2_500M_ok", "2h_x2_50x"),
}
toks = {"Proposed": "dynamic", "Adapt": "adaptive_w4", "Static": "static"}
w("| ワークロード | Proposed 合計(s) | Adapt 合計(s) | Static 合計(s) | Proposed削減 vs Adapt | vs Static |")
w("|---|--:|--:|--:|--:|--:|")
ex1_ratio = {}
for name, (D, fq) in ex1.items():
    s = {m: series_total(f"{D}/benchmark_results_{tok}_{fq}.json") for m, tok in toks.items()}
    tot = {m: sum(v) for m, v in s.items()}
    n = len(s["Proposed"])
    ar = [s["Adapt"][t] / s["Proposed"][t] for t in range(n)]
    sr = [s["Static"][t] / s["Proposed"][t] for t in range(n)]
    ex1_ratio[name] = (ar, sr)
    w(f"| {name} | {tot['Proposed']:,.0f} | {tot['Adapt']:,.0f} | {tot['Static']:,.0f} | "
      f"{(tot['Adapt']-tot['Proposed'])/tot['Adapt']*100:.1f}% | "
      f"{(tot['Static']-tot['Proposed'])/tot['Static']*100:.1f}% |")
w()
w("各時刻比（Adapt/Proposed, Static/Proposed）:")
w()
w("| ワークロード | Adapt/Proposed 平均 | 最大 | Static/Proposed 平均 | 最大 |")
w("|---|--:|--:|--:|--:|")
for name, (ar, sr) in ex1_ratio.items():
    w(f"| {name} | {sum(ar)/len(ar):.2f} | {max(ar):.2f} | {sum(sr)/len(sr):.2f} | {max(sr):.2f} |")
w()

# ---------------------------------------------------------------- ex4
w("## 2. 容量変化と総実行時間 (ex4)")
w()
w("縦軸 = `total_benchmark_time`（クエリ実行 + マイグレーション、Static は初期MV構築込み）。")
w("データ: ex4_ok_cycle (24_2_10) / ex4_ok_mono (24_mono)。")
w()
ex4 = {
    "Cycles (24_2_10)": ("time_dependent_output/ex4_ok_cycle", "_24_2_10"),
    "Evolution and Stagnation (24_mono)": ("time_dependent_output/ex4_ok_mono", "_24_mono"),
}
ex4files = {"Adapt": "benchmark_results_adaptive_w4{s}.json",
            "Static": "benchmark_results_static{s}.json",
            "Proposed": "benchmark_results_dynamic{s}.json"}
for name, (base, suf) in ex4.items():
    w(f"### {name}")
    w()
    w("| 容量(MB) | Adapt(s) | Static(s) | Proposed(s) | Proposed削減 vs Static |")
    w("|--:|--:|--:|--:|--:|")
    for cap in [500, 1000, 1500, 2000]:
        r = {m: bt(f"{base}/b{cap}/{fn.format(s=suf)}") for m, fn in ex4files.items()}
        w(f"| {cap} | {r['Adapt']:,.0f} | {r['Static']:,.0f} | {r['Proposed']:,.0f} | "
          f"{(r['Static']-r['Proposed'])/r['Static']*100:.1f}% |")
    w()

# ---------------------------------------------------------------- ex3_500M pruning
w("## 3. 候補プルーニング有無の比較 (ex3_500M_ok)")
w()
w("最適化時間 = pruning_time + solve_time（without は solve のみ）。目的関数値 = -objective/1000。")
w()
ex3 = {"Cycles": "24_2_10", "Evolution and Stagnation": "24_mono", "Growth and Spikes": "24_peak"}
D3 = "time_dependent_output/ex3_500M_ok"
w("| パターン | 候補 全→有望(削減%) | opt時間 wo→wp (高速化) | solve wo→wp | 目的値劣化 | 総実行時間 wo→wp |")
w("|---|---|---|---|--:|---|")
for name, fq in ex3.items():
    wp = json.load(open(f"{D3}/td_mv_optimization_result_{fq}.json"))
    wo = json.load(open(f"{D3}/td_mv_optimization_result_{fq}_wo.json"))
    pi = wp["pruning_info"]; tot, prom = pi["total_candidates"], pi["promising_candidates"]
    owp = wp.get("pruning_time_sec", 0) + wp["solve_time_sec"]
    owo = wo["solve_time_sec"]
    bwp = bt(f"{D3}/benchmark_results_dynamic_{fq}.json")
    bwo = bt(f"{D3}/benchmark_results_dynamic_{fq}_wo.json")
    objwp, objwo = -wp["objective"]/1000, -wo["objective"]/1000
    w(f"| {name} | {tot:,}→{prom:,}({(1-prom/tot)*100:.1f}%) | "
      f"{owo:.0f}→{owp:.0f}s (×{owo/owp:.2f}) | "
      f"{wo['solve_time_sec']:.0f}→{wp['solve_time_sec']:.0f}s | "
      f"+{(objwo-objwp)/objwo*100:.3f}% | {bwo:,.0f}→{bwp:,.0f} ({(bwp-bwo)/bwo*100:+.2f}%) |")
w()

# ---------------------------------------------------------------- scaling: queries
w("## 4. クエリ数スケーラビリティ (scaling_pruning)")
w()
w("最適化時間 = phase_time_sec を時間換算。No Pruning は 24h で打ち切り(DNF)。job-ceb-2-q{N}, 24_mono。")
w()
w("| クエリ数 | 候補 全→有望(削減%) | With Pruning(h) | No Pruning(h) | Static(h) | WP/Static | NoPr/WP |")
w("|--:|---|--:|--:|--:|--:|--:|")
for N in [20000, 40000, 60000, 80000, 100000]:
    b = f"time_dependent_output/job-ceb-2-q{N}"
    wp = json.load(open(f"{b}/td_mv_optimization_result_24_mono_wp.json"))
    st = json.load(open(f"{b}/static_mv_optimization_result_24_mono.json"))["execution_time"]
    pi = wp["pruning_info"]; tot, prom = pi["total_candidates"], pi["promising_candidates"]
    wpph = wp["phase_time_sec"]
    nopath = f"{b}/td_mv_optimization_result_24_mono.json"
    if os.path.exists(nopath):
        noph = json.load(open(nopath))["phase_time_sec"]
        noh, ratio = f"{noph/H:.2f}", f"{noph/wpph:.1f}"
    else:
        noh, ratio = "DNF", "-"
    w(f"| {N//1000}k | {tot:,}→{prom:,}({(1-prom/tot)*100:.1f}%) | {wpph/H:.2f} | {noh} | {st/H:.2f} | "
      f"{wpph/st:.2f} | {ratio} |")
w()

# ---------------------------------------------------------------- scaling: timesteps
w("## 5. タイムステップ数スケーラビリティ (scaling_timestep)")
w()
w("クエリセット固定(2500)→候補数一定。最適化時間 = phase_time_sec(s)。result_scaling_time_ok。")
w()
w("| TS | 候補 全→有望(削減%) | With Pruning(s) | No Pruning(s) | NoPr/WP |")
w("|--:|---|--:|--:|--:|")
Dts = "time_dependent_output/job-ceb-2/result_scaling_time_ok"
for ts in [12, 18, 24, 30, 36, 42]:
    wp = json.load(open(f"{Dts}/td_mv_optimization_result_{ts}_mono_wp.json"))
    wo = json.load(open(f"{Dts}/td_mv_optimization_result_{ts}_mono_wo.json"))
    pi = wp["pruning_info"]; tot, prom = pi["total_candidates"], pi["promising_candidates"]
    wpph, woph = wp["phase_time_sec"], wo["phase_time_sec"]
    w(f"| {ts} | {tot:,}→{prom:,}({(1-prom/tot)*100:.1f}%) | {wpph:.0f} | {woph:.0f} | ×{woph/wpph:.2f} |")
w()

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print("wrote", OUT)
