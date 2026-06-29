# 並列プルーニングのデータ受け渡しを共有メモリ(CSR)化

作成日: 2026-06-25

## 背景・問題

CFプルーニングの並列実装 `_prune_candidates_parallel`（`--pruning-parallel`）は、各タスク（WSTノード）の `executor.submit(...)` に `u_ij`/`X` を**引数として渡していた**。`ProcessPoolExecutor` はワーカーが別プロセスのため、これらが**タスクごとにpickle化・IPC転送**されていた。

- 大規模合成セットの `u_ij`/`X` は「**疎だが dict/set ＋ Pythonオブジェクト**」表現で重い（q100000 で pickle 約13GB級）。
- これをタスク数ぶん転送 → **時間（直列化）もメモリ（ワーカー数ぶんの複製）も浪費**。
- 逐次実行は同一プロセス・参照共有なので、この問題は発生していなかった（並列特有）。

## 解決方針：`multiprocessing.shared_memory` ＋ CSR

3条件をすべて満たす方式を採用：
- **Linux非依存**（fork/spawn 両対応）
- **pickle転送ゼロ**（ワーカーへ渡すのは共有メモリの名前・メタ情報だけ）
- **物理1コピー共有**（全ワーカーが同じバッファをマップ／GIL無関係の真のプロセス並列）

dict/set はそのまま共有メモリに置けないため、疎構造を**フラットなCSR配列**へ変換：
- `u_ij` → `indptr`/`col`/`data`（行は列でソート）
- `X` → `indptr`/`idx`（行ソート、membership は searchsorted）

これは並列の転送問題を解くだけでなく、**dict表現の重さ自体の軽量化**にもなる（オブジェクトオーバーヘッド除去）。

## 変更ファイル

- `core/sparse_structures.py`
  - 共通読み取りAPIの基底クラス `SparseMatrixBase`/`SparseXBase`（`iter_rows()`, `row_items(i)`, `children(j)`）を追加。既存 `SparseMatrix`/`SparseX` をサブクラス化（**挙動不変**：`iter_rows` は従来のdict走査と同一を返す）。
  - CSR＋共有メモリ版 `SharedSparseMatrix`/`SharedSparseX`、CSRビルダー `build_u_csr`/`build_x_csr`、SHMヘルパー `put_array_to_shm`/`attach_array_from_shm` を追加。
- `core/local_ilp_optimizer.py`
  - スパース分岐の検出を `isinstance(x, SparseMatrixBase)` に、走査を `iter_rows()` に変更。→ **dict版（逐次）でも CSR/SHM版（並列ワーカー）でも同一コードで読む**。
- `core/cf_pruner.py`
  - `_prune_candidates_parallel` を「CSRを1回構築 → 共有メモリへ配置 → **単一プール＋`initializer=_pp_init`**（ワーカーが名前でアタッチ）→ タスクは `node` と親境界集合だけ送る」に変更。レベル単位BFS・親子境界制約は従来どおり維持。
  - 密 list-of-lists（元の job-ceb-2）は従来の per-task 受け渡しにフォールバック。
  - 終了時に `executor.shutdown(wait=True)` 後 SHM を `close()`+`unlink()`。

## 既存処理への影響

- **逐次プルーニング・他の最適化器（dynamic本体・bigsubs・utility・adaptive/peloton）・recalc・weighted_u_ij は無変更**。`SparseMatrix` に共通メソッドを足しただけで、`.rows` も残存。
- ワーカーで SHM を読むのは `LocalILPOptimizer` のみ（他はメインプロセスで dict 版を使用）。

## 検証（job-ceb-2-x2: I=5,030 / J=51,073）

| | 有望MV | プルーニング時間 | ILP求解 |
|---|---|---|---|
| 逐次（改修後） | 2,920/51,073 (94.3%) | 392秒 | 13.6秒 |
| **並列(8ワーカー)** | **2,920/51,073 (94.3%)** | **214秒** | 13.9秒 |

- **有望MV集合が完全一致**（2,920＝2,920）→ プルーニングの方法・結果は逐次と同一。
- 並列は約1.8倍高速、セグフォ無し、per-taskのpickle転送ゼロ。
- CSR↔dict の等価性（u行・X隣接・`[i][j]`/membership）も単体確認済み。
- 逐次は改修前（2,920・390秒）と一致＝**回帰なし**。

## 実行方法・注意

```bash
.venv/bin/python scripts/run_experiment_normal.py --phase 6 \
  --query-set job-ceb-2-q20000 --optimization-mode dynamic \
  --use-pruning --pruning-parallel --pruning-workers 16 \
  --exp-suffix _24_mono --b-max 500 --recalc
```

- **`--pruning-workers` を指定推奨**（既定は `cpu_count()`=64）。64ワーカー × Gurobi内部スレッドで**オーバーサブスクリプション**になりうるため 16 程度が無難。WSTノードは約47個・浅い階層は兄弟が少ないので16でも十分使い切れる。
- `u_ij`/`X` は共有メモリで1コピー。増えるのは initializer 経由の中規模データ（`node_list`/`migration_cost`/`freq` 等）のワーカー数ぶんのみ。
- 実装上の注意：共有メモリ上の numpy 配列は SHMハンドルをGCすると segfault するため、ワーカー側で `_PP_CTX["_shms"]` に保持している（対処済み）。終了時の resource_tracker 警告が出る場合があるが機能には影響しない。
