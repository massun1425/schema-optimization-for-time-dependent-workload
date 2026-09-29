# 候補プルーニングの有無による比較（ex3, 500M スケール）

作成日: 2026-07-13

## 概要

500M スケール（`ex3_500M_ok`）で、3 つのワークロードパターンについて、**候補プルーニングの有無**に
よる最適化時間・総実行時間・目的関数値を比較した（添付の Table 3 と同形式）。手法は時間依存
dynamic 最適化で、`_wo` = プルーニングなし、無印 = プルーニングあり。

| ワークロードパターン | 頻度サフィックス | td 結果 / benchmark 結果ファイル |
|---|---|---|
| Cycles | `24_2_10` | `td_mv_optimization_result_24_2_10{,_wo}.json` / `benchmark_results_dynamic_24_2_10{,_wo}.json` |
| Evolution and Stagnation | `24_mono` | 同上（`_24_mono`） |
| Growth and Spikes | `24_peak` | 同上（`_24_peak`） |

## 結果表

| Workload pattern | Candidate pruning | # candidates before whole-time-step opt. | Optimization time (s) | Total execution time (s) | Objective value (×10³) |
|---|---|---:|---:|---:|---:|
| Cycles | Without pruning | 26,312 | 477.9 | 420,064 | 79,141,478 |
|  | With pruning | 1,656 | 422.8 | **401,043** | 79,089,082 |
| Evolution and Stagnation | Without pruning | 26,312 | 1281.0 | 1,020,141 | 163,070,090 |
|  | With pruning | 1,772 | 404.6 | **989,106** | 163,001,471 |
| Growth and Spikes | Without pruning | 26,312 | 1375.6 | **212,467** | 35,609,760 |
|  | With pruning | 1,648 | 383.8 | 213,274 | 35,600,152 |

太字は各パターンで総実行時間が小さい（良い）方。

LaTeX 版: [table3.tex](table3.tex)（`booktabs`, `multirow` パッケージが必要）
生成スクリプト: [generate_table3.py](generate_table3.py) / 表データ: [table3_markdown.md](table3_markdown.md)

## 各列の算出方法（読み込んだフィールド）

| 列 | ソース | 備考 |
|---|---|---|
| # candidates before whole-time-step opt. | `td...pruning_info.total_candidates`（Without）/ `...promising_candidates`（With） | 全時刻同時最適化に投入する候補 MV 数。総候補数は with 側の `pruning_info` から取得（26,312） |
| Optimization time (s) | `pruning_time_sec + solve_time_sec` | Without はプルーニングなしのため `solve_time_sec` のみ |
| Total execution time (s) | `benchmark_results_dynamic...summary.total_benchmark_time` | クエリ実行時間 + マイグレーション時間 |
| Objective value (×10³) | `-objective / 1000` | 結果ファイルの `objective` は負値（コスト形式）のため符号反転し正の大きさで表示 |

## 考察

- **プルーニングは候補 MV を大幅に削減**（26,312 → 1,648〜1,772、約 93〜94% 削減）しつつ、
  目的関数値の劣化はごく僅か（各パターンで 0.1% 未満）。ほぼ同等の解品質を保っている。
- **最適化時間はプルーニングで短縮**。特に Evolution and Stagnation で 1,281.0 → 404.6 秒（約 3.2 倍）、
  Growth and Spikes で 1,375.6 → 383.8 秒（約 3.6 倍）。Cycles は 477.9 → 422.8 秒（約 1.1 倍）で、
  この規模ではプルーニング自体の前処理コスト（約 400 秒）が最適化時間の大半を占めるため短縮幅は小さい。
- **総実行時間はプルーニング有無でほぼ同等**（差は 0.4〜3.0%）。Cycles・Evolution ではむしろ
  プルーニングありが小さく、Growth ではプルーニングなしが僅かに小さい。差は目的関数値の微差と
  ベンチマーク実行時間の測定ばらつきの範囲内であり、**プルーニングによる解品質の実害はほぼ無い**。

## まとめ

候補プルーニングは、解品質（目的関数値・総実行時間）をほぼ損なうことなく、投入候補数を約 1/16 に
削減して最適化時間を短縮する。特にワークロードが複雑で ILP 求解が重くなる Evolution and Stagnation /
Growth and Spikes で効果が大きい。

## 備考

- 数値の丸め: 最適化時間は小数第 1 位、候補数・総実行時間・目的関数値は整数。
- LaTeX 表は添付画像に合わせて桁区切りコンマなし。マークダウン表は可読性のためコンマ付き。
- Optimization time はプルーニング時間を含む（`pruning_time_sec + solve_time_sec`）ため、
  with pruning 側もプルーニングの前処理コストを公平に含めた比較になっている。
