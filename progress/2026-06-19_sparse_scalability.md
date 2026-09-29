# スケーラビリティ検証のためのスパース化対応

作成日: 2026-06-19

## 目的

`scripts/run_experiment_normal.py` の最適化について、**クエリ数を擬似的に増やして最適化時間のスケーラビリティを検証**する。ベンチマーク（DB実行）は行わず、最適化フェーズのみを評価する。実行可能な実クエリを用意するのは困難なため、既存の `job-ceb-2`（2,515クエリ）の構造を擬似的に拡張する。

## 判明した根本問題：密行列表現

実パース結果（`03_parsed/job-ceb-2/qp_class.pkl`）は `u_ij`・`X` を**密な list-of-lists** で保持していた。

| 構造 | 形 | 現状サイズ | 非ゼロ |
|---|---|---|---|
| `u_ij` | 2,515 × 26,312 | 6,617万セル | 43,593 (0.07%) |
| `X` | 26,312 × 26,312 | **6.9億セル** | 302,582 (0.04%) |
| pickle | — | **2.87 GB** | — |

`X` は J×J の密行列のため、K倍スケールで `X` のセル数が K² で増え、**K=2でも約11GB、20k/40kでは物理的に不可能**。さらに最適化器側も `for i: for j: if u_ij[i][j]>0` という **O(I×J)**（静的normalの包含制約は **O(I·J²)**）の密走査前提だった。

→ 「pickleを大きくして読ませる」方式は破綻。**スパース表現**にすれば u_ij≈70万・X≈480万エントリ（K=16時）で問題なく扱える。

## 採用した方式：実ブロックのK倍タイル複製（スパース）

`job-ceb-2` の実構造を1ブロックとしてK個複製する。

- **共有率は実測に忠実**：fan-out≥2 の 1,551ノード（6%）を全ブロック共通、残り 94%（24,761）の private ノードをブロックごとに複製（ID に `__r{k}`）。実測の低共有・ほぼ線形なJ成長（J/n≈10、末尾8.2新ノード/クエリ）を再現。
- **ブロック内の共有・包含(X)は実データそのまま**（サブ行列をコピー）。
- **コスト・サイズ・利得は複製ブロックに±eps摂動**（既定5%）。Gurobiが対称性を悪用して非現実的に速く解くのを防ぐため。block0は無摂動。
- **頻度は既存パターン（例 `_24_mono`）を流用**。新規頻度は作らない。

## オプトイン方式（既存実験を壊さない）

**フラグ不要**。合成クエリセット名（例 `job-ceb-2-x8`）を `--query-set` に渡すだけ。最適化器は `isinstance(u_ij, SparseMatrix)` で自動分岐する。既存の密パスは全て `else` 側に温存しており、**既存クエリセットの実験は同一コード・同一結果**で動く。NormalOptimizer（static `normal`/`both`）は密専用のため未対応（スケーラビリティ用シェルでは未使用）。

## 追加・変更ファイル

### 新規
- `core/sparse_structures.py` — `SparseMatrix`/`SparseX`/`SparseQM`/`SparseQP`。`m[i][j]` は0デフォルトで動き（密コードと互換）、非ゼロ走査メソッドも持つドロップイン型。
- `scripts/extract_sparse_base.py` — 密pickle→コンパクトな疎base（`03_parsed/<set>/sparse_base.pkl`、一度だけ・約40秒・136MB）。X の J×J 密走査を毎回避けるため。
- `scripts/generate_synthetic_scaling.py` — 疎baseをK倍タイルし、`03_parsed/<set>/qp_class.pkl`（SparseQP）・`04_migration/<set>/simple_migration_costs.json`・`01_queries/<set>/frequency_time_dependent<suffix>.json` を出力。

### 変更（密ホットスポットに `isinstance` でスパース分岐を追加、密経路は不変）
- `core/time_dependent_optimizer.py` — `initialize_candidates`, `_build_sparse_utility_index`（dynamic）
- `core/local_ilp_optimizer.py` — 同上（CFPruner内の局所ILP）
- `core/cf_pruner.py` — `_initialize_candidates`
- `core/two_step_optimizer.py` — 同上（adaptive/peloton）
- `core/utility_v2.py` — `initialize_greedy` の U_j_max、候補初期化×2
- `src/optimization/bigsubs.py` — U_j_max、y_ij を per-query 選択リスト（疎）化、`local_ilp_selected` 追加、`M_i_` の毎クエリ再計算を1回/反復に
- `src/optimization/base.py` — `solve_ilp_with_candidates` の dense ret_y を疎化
- `scripts/run_experiment_normal.py` — recalc の u_ij 更新ループ、静的の weighted_u_ij 構築をスパース分岐

## 検証結果（K=2: I=5,030 / J=51,073 / u_nnz=87,186 / X_nnz=600,545）

| モード | 結果 |
|---|---|
| static bigsubs | 35反復 / 128秒 / MV 1,685 |
| dynamic + pruning | プルーニング 94.3%削減 / 390秒 ＋ ILP求解 13.6秒 |
| static utility | MV 2,338 |
| adaptive (w=4) | 350秒 / 24時点完走 |

block0 が原データと完全一致、頻度の自然順＝行順の整合も確認済み。

## 使い方

```bash
# 1. (一度だけ) 密 → 疎base 抽出
.venv/bin/python scripts/extract_sparse_base.py --query-set job-ceb-2

# 2. 目標クエリ数で生成（--queries でぴったりの値に切り詰め）
.venv/bin/python scripts/generate_synthetic_scaling.py --base-set job-ceb-2 --queries 20000 --freq-suffix _24_mono

# 3. 最適化時間を計測（例: pruning付き dynamic）
.venv/bin/python scripts/run_experiment_normal.py --phase 6 --query-set job-ceb-2-q20000 \
  --optimization-mode dynamic --use-pruning --exp-suffix _24_mono --b-max 500 --recalc
```

注: 実行は `.venv/bin/python`（システムpythonは3.8、本プロジェクトは3.12が必要）。Gurobi はアカデミックライセンス使用。
