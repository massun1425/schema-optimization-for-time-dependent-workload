# 論文実験スクリプト（EDBT2026 "Schema Optimization for Time-Dependent Workloads"）

論文に載せている結果を得るためのシェルスクリプト群。実験本体は `scripts/run_experiment_normal.py`。
結果は `time_dependent_output/rq*/` にまとめる。既存の結果（`*_ok` など）には手を触れない。

## 構成

| スクリプト | 論文 | 内容 | 出力先 |
|---|---|---|---|
| `00_prepare.sh` | — | Phase 1〜5 + コスト再計算（job-ceb-2, Redbench_synthetic） | `02_json/`, `03_parsed/`, `04_migration/`（既存ならスキップ） |
| `rq1_exp1_1_timestep_time.sh` | Fig.7 | 各時刻の実行時間（3パターン + Redbench, 3手法） | `time_dependent_output/rq1/exp1_1/{job-ceb-2,Redbench_synthetic}/` |
| `rq1_exp1_2_timestep_scaling.sh` | Fig.8 | 最適化時間 vs タイムステップ数（T=12〜42, プルーニング有無） | `time_dependent_output/rq1/exp1_2/` |
| `rq1_exp1_3_query_scaling.sh` | Fig.9 | 最適化時間 vs クエリ数（20k〜100k, Static / 有 / 無） | `time_dependent_output/rq1/exp1_3/job-ceb-2-q{N}/` |
| `rq2_prediction_recall.sh` | Fig.10 | recall（= 100 − noise）に対する頑健性 | `time_dependent_output/rq2/` |
| `rq3_pruning.sh` | Table 2 | プルーニング有無の比較 | `time_dependent_output/rq3/` |
| `rq4_capacity.sh` | Fig.11 | 容量制約 500〜2000MB | `time_dependent_output/rq4/{24_2_10,24_mono,24_peak}/b{500..2000}/` |
| `run_all.sh` | — | 上記を依存順に実行 | |
| `common.sh` | — | 共通の設定・関数（source 専用） | |

各出力先には結果 JSON と `log/`（実行ログ）が置かれる。

## 実行条件（論文の結果 JSON と照合済み）

- 共通: `--recalc`、B_max = 500MB（RQ4 以外）、T = 24、ベンチマークは `--ease`（各クエリを1回実行し頻度倍）
- 頻度ファイル: job-ceb-2 は `_24_2_10` / `_24_mono` / `_24_peak`（**`_rand` 版ではない**）、Redbench は `_2h_x2_50x`
- Proposed: `--optimization-mode dynamic --use-pruning`
  - Fig.7 / Table 2 / Fig.11 の b500 は逐次プルーニング
  - Fig.8 / Fig.11 の b1000 以上は `--pruning-parallel`、Fig.9 は `--pruning-parallel --pruning-workers 16`
  - （元の実行どおり。有望 MV 集合は逐次と並列で同一だが、プルーニング時間は異なる）
- Static: `--optimization-mode static --static-timestep average --static-algorithm utility`
- Adapt: `--optimization-mode adaptive --window-size 4 --freq-weight linear`
- プルーニングなし: 1実行あたり 24h で打ち切る。超えたら DNF とし、それより大きい規模は実行しない

## 結果の再利用（論文データと同じ扱い）

同一条件の実行は1回だけ行い、コピーして共有する（`REUSE=1` が既定）:

- RQ2 の recall 100% ← RQ1 Exp1-1 の Redbench 結果
- RQ3 の With pruning ← RQ1 Exp1-1 の Proposed
- RQ4 の b500 ← RQ1 Exp1-1 の3手法

そのため `run_all.sh` は Exp1-1 を最初に実行する。
RQ2 のノイズ実験は最適化をやり直さない。recall 100% の最適化結果から Phase 7/8 を再生成し、Phase 9 だけを実行する。

## staging と既存ファイルの扱い

`run_experiment_normal.py` は結果を `time_dependent_output/<query_set>/` 直下（staging）に固定名で書き出す。
staging には既存の結果（例: `job-ceb-2-q{N}/` にある Fig.9 の元データ）も置かれているため、各スクリプトは次のように動く:

1. **結果 JSON**: 実行の直前に、これから書き込まれる名前と衝突する既存ファイルだけを `<set>/_stash/in_use/` へ一時退避する。
   結果を `rq*/` へ移動したら、元の場所へ戻す。異常終了や中断のときも EXIT 時に戻す（元の場所が空いている場合のみ）。
   → **既存の結果は実行後も元のパスに残る。**
2. **中間生成物**（`timestep_*.sql`, `static_*initial_mvs.sql`, `jobs/`）: Phase 7/8 が削除して作り直すため、
   post-opt 系スクリプトの初回だけ `<set>/_stash/intermediates_<日時>/` へ退避する（`.paper_staging` が目印）。
   現在残っているものは論文の結果とは対応していない（最後の実行のもの）が、念のため残す。
3. 1回実行するごとに、結果を `rq*/` へ移動する（プルーニングなしの実行は `_wo`、ありは `_wp` を付ける）。
4. 出力先に結果が既にある実行はスキップする。途中で止まっても再実行すれば再開できる。

中断後に `_stash/in_use/` にファイルが残っている場合は、元の場所に中断時の途中出力があることを意味する。
手動で確認してから片付けること（その場合、次の実行は安全のため停止する）。

## 環境変数

| 変数 | 既定 | 意味 |
|---|---|---|
| `DRY_RUN` | 0 | 1 なら実行せずコマンドを表示する（ファイル操作もしない） |
| `FORCE` | 0 | 1 なら結果があっても再実行・再コピーする |
| `REUSE` | 1 | 0 なら RQ1 の結果を再利用せず、各 RQ で実行する |
| `PY` | `.venv/bin/python` | Python 3.12 環境 |
| `CONTAINER` | `mv_postgres` | PostgreSQL コンテナ名（ベンチマーク前に再起動する） |
| `TIMEOUT` | `24h` | プルーニングなし最適化の打ち切り時間 |
| `SUFFIXES` / `CAPS` / `TIMESTEPS` / `QUERY_COUNTS` / `NOISE_PCTS` / `SETS` | 論文の値 | 一部だけ実行したいときに上書きする（例: `SUFFIXES="_24_mono"`） |
| `SKIP_REDBENCH` | 0 | Exp1-1 で Redbench を飛ばす |
| `FORCE_PREP` | 0 | 1 なら前処理を再生成する（既存は `<dir>/<set>__backup_<日時>` へ退避） |

## 使い方

```bash
# 実行されるコマンドの確認（何も実行・変更しない）
DRY_RUN=1 bash paper/run_all.sh

# 全実験
nohup bash paper/run_all.sh > paper_run_all.log 2>&1 &

# 個別に実行
bash paper/rq3_pruning.sh
SUFFIXES="_24_peak" CAPS="1000" bash paper/rq4_capacity.sh
```

## 前提・既知の問題

- PostgreSQL コンテナ（`mv_postgres`）が起動していること。Phase 6 だけの実験（Exp1-2, Exp1-3）は DB 不要。
- **`Dockerfile` の `COPY ./data/...` はリンク切れ**（実体は `archive/data/`）。コンテナを新しく作るときは修正が必要。
- Gurobi ライセンス（`gurobi.lic` / `.env` の `GRB_LICENSE_FILE`）が必要。
- 論文結果の JSON には記録されておらず、元のシェルスクリプトの記述に合わせた条件:
  - Adapt の `--freq-weight linear`
  - 前処理のサンプリング率（job-ceb-2 = high、Redbench = low）
- 図の生成スクリプト（`progress/*/plot_*.py` など）は、まだ旧パス（`*_ok`）を読む。`rq*/` 構成向けの版は別途用意する。
- 論文図表と旧データの対応は `progress/2026-09-28_paper_experiment_inventory.md` を参照。
