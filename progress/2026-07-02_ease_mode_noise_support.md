# easeモードでの noise-ratio 高速ベンチマーク対応

作成日: 2026-07-02
対象: ノイズ注入付きベンチマーク（`--noise-ratio`）を easeモードでも高速に実行できるようにする
関連ファイル:
- `benchmark/time_dependent_query_executor.py`
- `scripts/run_experiment_normal.py`
- `scripts/shell/run_ex2_redbench_robust.sh`

## 背景・課題

- **easeモード**は「各クエリを1回だけ実行し、その実測時間 × 頻度」で各時刻の総実行時間を推定する高速モード。
- 一方で **noise注入**（書き換え前の元クエリを一定割合で混ぜて実行する）は従来 **通常モードのみ**で有効だった。通常モードは `frequency` 回だけ実際に実行するため、頻度が大きいと非常に時間がかかる。
- そのため ease + noise は無効化されており、noise-ratio を指定した堅牢性実験が実質的に高速実行できなかった。

## 変更内容

### 1. easeモードでの noise 推定ロジックを追加

`benchmark/time_dependent_query_executor.py` の `_execute_queries_with_frequency` に、easeモード時の noise 分岐を実装。

各時刻・各クエリについて **実行は2回だけ**:

1. 書き換え後クエリを1回実行 → `t_rewritten`
2. 元（書き換え前）クエリを1回実行 → `t_original`（`noise_pool` から stem で取得）

推定合計時間は頻度を分割して算出:

```
noise_count     = round(frequency × noise_ratio)   # 四捨五入 (round half up)
rewritten_count = frequency − noise_count           # 残り（合計 = frequency を維持）
estimated_total = t_original × noise_count + t_rewritten × rewritten_count
```

- **合計実行回数は常に `frequency` を維持**し、noise分の回数のみ四捨五入する方針。
- これは通常モードで noise を確率的に流したときの **期待値と一致**し、easeモード本来の「時間×頻度」の思想とも整合する。
- 元クエリが `noise_pool` に無い場合や noise_ratio=0 の場合は、従来どおり `t_rewritten × frequency`（noiseなし）にフォールバック。
- 結果JSONに `noise_time` / `noise_count` / `rewritten_count` / `noise_applied` を追記。

`use_noise` 判定から `not ease_mode` の条件を除去し、easeモードでも noise を有効化。

### 2. noise_pool のロードを easeモードでも実行

`scripts/run_experiment_normal.py` の phase9 で、noise_pool のロード条件を
`noise_ratio > 0.0 and not ease_mode` → `noise_ratio > 0.0` に変更。
easeモードでも元クエリのプールを事前ロードするようにした。docstring と `--noise-ratio` のヘルプも実挙動に合わせて更新。

### 3. 実験スクリプト（`run_ex2_redbench_robust.sh`）

- **Dynamic** と **Static** の noise-ratio 0.05〜0.40 実験がこのスクリプトで実行可能なことを確認。
  - 0.05 は post-opt 実行時に生成、0.10〜0.40 は phase 9 のみのループで生成。
- Adaptive は今回の対象外（ブロックはコメントアウトのまま）。

## 分割計算の確認例

| freq | ratio | noise_count | rewritten_count | 合計 |
|---:|---:|---:|---:|---:|
| 10 | 0.30 | 3 | 7 | 10 |
| 1 | 0.30 | 0 | 1 | 1 |
| 1 | 0.50 | 1 | 0 | 1 |
| 5 | 0.50 | 3 | 2 | 5 |
| 3 | 0.25 | 1 | 2 | 3 |

合計は常に `freq` に保たれる。

## 効果

- ease + noise でクエリあたりの実行が **2回**（書き換え後・元）で済むため、頻度が大きくても高速。
- 通常モードで確率的に noise を流したときの期待値とほぼ一致する推定が得られる。
