# 論文図表スクリプト

`paper/*.sh` の実行結果（`time_dependent_output/rq*/`）から、論文に載せている図表だけを生成する。
描画コードは論文の図を作った既存スクリプトからの移植で、変えたのは入力パスと出力先だけ。
スクリプト名・出力ファイル名は `paper/` と同じく RQ・実験番号に対応させている（`setup_` は 5.1 節の実験設定の図）。

## 図表と入出力

出力先はすべて `paper_figures/output/`（`--out-dir` で変更可）。入力の `rq*/` は `time_dependent_output/` 以下。

| スクリプト | 論文 | 出力 | 入力 |
|---|---|---|---|
| `setup_frequency_patterns.py` | Fig.5 | `setup_frequency_pattern_{Cycles,Evolution_and_Stagnation,Growth_and_Spikes}.pdf` | `01_queries/job-ceb-2/frequency_time_dependent_{24_2_10,24_mono,24_peak}.json` |
| `setup_redbench_total_count.py` | Fig.6 | `setup_redbench_total_count.pdf` | `01_queries/Redbench_synthetic/frequency_time_dependent_2h_x2_50x.json` |
| `rq1_exp1_1_timestep_time.py` | Fig.7 | `rq1_exp1_1_timestep_time_{cycles,evolution_and_stagnation,growth_and_spikes,redbench_synthetic}.pdf` | `rq1/exp1_1/` |
| `rq1_exp1_2_timestep_scaling.py` | Fig.8 | `rq1_exp1_2_timestep_scaling.pdf` | `rq1/exp1_2/` |
| `rq1_exp1_3_query_scaling.py` | Fig.9 | `rq1_exp1_3_query_scaling.pdf` | `rq1/exp1_3/` |
| `rq2_prediction_recall.py` | Fig.10 | `rq2_prediction_recall.pdf` | `rq2/` |
| `rq3_pruning.py` | Table 2 | `rq3_pruning.tex`, `rq3_pruning.md` | `rq3/` |
| `rq4_capacity.py` | Fig.11 | `rq4_capacity.pdf` | `rq4/` |

各スクリプトの docstring に、使うファイルとフィールドの定義を書いてある。

## 使い方

```bash
bash paper_figures/make_all.sh                            # すべて生成
.venv/bin/python paper_figures/rq1_exp1_1_timestep_time.py   # 個別に生成

# 入力・出力先を変える（全スクリプト共通の引数）
bash paper_figures/make_all.sh --td-dir <rq* を含むディレクトリ> --out-dir <出力先>
```

入力が足りない場合は、不足しているファイルを一覧表示してエラー終了する。
RQ1 Exp1-3 のプルーニングなしは、結果 JSON か `DNF_24_mono_wo.txt`（`paper/rq1_exp1_3_query_scaling.sh` が書く）のどちらかが必要。

PDF には作成日時を埋め込まないため、同じ入力からは同じ PDF が得られる。
