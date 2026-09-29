# Peloton（1ステップ先読み）モード追加 ＆ 最終ステップ最適化スキップ

- **日付**: 2026-06-18
- **対象**: `scripts/run_experiment_normal.py`
- **前提**: [`2026-06-18_bigsubs_adaptive_refactor.md`](2026-06-18_bigsubs_adaptive_refactor.md) の変更（便益モデル統一・案B初期化・線形減衰）の続き

---

## 0. 概要

2つの変更を行った。

1. **Peloton モードの追加** — 「1ステップ先の実頻度を完全予知して逐次最適化する」比較手法を新設。
2. **最終タイムステップの無駄な最適化をスキップ** — adaptive / peloton 共通。結果が使われない最終ステップのILPを省略。

加えて、検証の過程で確認した **TwoStep の prev_freq（1つ目の頻度）が結果に無関係**である点も記録する。

---

## 1. 既存手法との位置づけ

Peloton は自己運転DB（Pavlo et al., *Self-Driving Database Management Systems*, CIDR 2017）の **予測駆動の事前最適化**を、1ステップ先を完全予知できる理想版として表現するベースライン。

| 手法 | 予測 | 視野 | 結果ファイル |
|------|------|------|-------------|
| Static (BigSubs) | なし | 単一時刻 | `static_bigsubs_optimization_result{suffix}.json` |
| **Adaptive** | **過去**の重み付き移動平均（反応型） | 近視眼的(1ステップ) | `adaptive_mv_optimization_result_w{W}{suffix}.json` |
| **Peloton（新規）** | **1つ先の実頻度**（予測型・完全予知） | 近視眼的(1ステップ) | `peloton_mv_optimization_result{suffix}.json` |
| Dynamic | 全期間既知 | 全期間 | `td_mv_optimization_result{suffix}.json` |

- **Adaptive**: 直近の観測（過去）から将来を推測 → 反応型。予測誤差あり。
- **Peloton**: 次時刻の実際の頻度を知った上で構成を準備 → 予測型・完全予知。「1ステップだけ未来が分かる」理想ケース。
- いずれも移行コストを考慮した近視眼的逐次最適化で、便益モデルは統一済み TwoStep（複数MV可）を共有。
- Dynamic（全期間一括）との差は「視野（全期間 vs 1ステップ）」に帰着する。

---

## 2. 変更点① Peloton モードの追加

### 2.1 アルゴリズム

- **初期解 `z_0`**: 空集合 + 時刻0頻度で構築（Adaptive の案Bと同一: `TwoStepOptimizer(fixed_mvs=set(), curr_freq=freq[0], migration_cost=実コスト)`）
- **各遷移**: `z_{t+1} = TwoStep(fixed=z_t, curr_freq=freq[t+1])`
  - ウィンドウなし。**1つ先の時刻の実頻度をそのまま** `curr_freq` に使用。
  - 結果として各時刻 `z_s` はその時刻の実頻度 `freq[s]` で最適化される（完全1ステップ予知）。
- migration から z_{t+1} を決める論理は Adaptive と同じ（`fixed=現構成`, 新規作成分のみコスト計上）。

### 2.2 実装方針（重複最小化）

`phase6c_optimize_adaptive` に `lookahead: bool = False` フラグを追加し、Adaptive と機構を共有しつつ**頻度ソースだけ切り替える**。

```python
def phase6c_optimize_adaptive(self, window_size=None, b_max=None, lookahead=False):
    ...
    if not is_last:
        if lookahead:
            # Peloton: 1つ先の実頻度をそのまま使用（ウィンドウなし）
            src_freq = frequencies[timesteps[t + 1]]
            curr_freq = [src_freq[i] if i < len(src_freq) else 1.0 for i in range(query_count)]
        else:
            # Adaptive: 過去 window_size 時刻の重み付き移動平均
            ...
```

- `phase6_optimize` に `elif mode == 'peloton': return self.phase6c_optimize_adaptive(b_max=b_max, lookahead=True)` を追加。
- 結果の `algorithm` フィールド = `"peloton_lookahead"`、ファイル名 = `peloton_mv_optimization_result{suffix}.json`（ウィンドウサイズ付かない）。

### 2.3 下流フェーズ（7/8/9）への配線

Peloton の結果は dynamic/adaptive と同じ**時間依存型**（タイムステップごとに構成が変わりマイグレーションあり）。各フェーズに `peloton` 分岐を追加：

| Phase | 対応 |
|-------|------|
| 7 (SQL生成) | `peloton` を時間依存型として処理、`peloton_mv_optimization_result{suffix}.json` を読む |
| 8 (クエリ書換) | 同上。rewritten queries は dynamic/adaptive と同じ `jobs/` を共有 |
| 9 (ベンチマーク) | `else`（dynamic/adaptive/peloton）分岐で `execute_time_dependent_benchmark`。出力 `benchmark_results_peloton{suffix}.json` |

argparse: `--optimization-mode` と `--benchmark-mode` の choices に `peloton` を追加。

### 2.4 実行コマンド

```bash
python scripts/run_experiment_normal.py \
  --phase post-opt \
  --query-set job-ceb-2 \
  --optimization-mode peloton \
  --exp-suffix _24_2_10_rand \
  --b-max 500 --recalc --use-docker --ease
```

---

## 3. 変更点② 最終タイムステップの最適化スキップ

### 3.1 背景の問題

旧実装（adaptive）は**最終タイムステップでも次MVの最適化を実行**していたが、その結果 `next_mvs` は記録対象（次のタイムステップ）が無いため**破棄**されていた。Peloton も同様。

- `TwoStepOptimizer` のインスタンス化（候補フィルタリング O(I×J)）+ ILP求解 が**無駄に1回**走る。

### 3.2 「結果ファイルへの反映」の実態（重要な確認）

旧実装で最終ステップの最適化結果がどう反映されていたか：

| 項目 | 旧実装での反映 |
|------|---------------|
| MV構成 (`z_by_timestep`) | **反映されない**（破棄） |
| 移行情報 (`migration_analysis` の構成) | **反映されない**（最終要素は「前→最終」の移行のみ） |
| ベンチマーク結果 | 影響なし |
| **計算時間** | **反映されていた**（← 例外）: `step_solve_times` が T件、最終の `solve_time_sec` に無駄な最適化時間が計上され、`total_optimization_time` / `avg_step_time` が1回分過大 |

つまり「**MV選択には無関係だが、最適化時間の集計だけが過大**」だった。

### 3.3 修正内容

`if not is_last:`（`is_last = (t + 1 >= len(timesteps))`）で以下を最終ステップ時にスキップ：
- 頻度集約（移動平均 / 先読み）
- `TwoStepOptimizer` のインスタンス化
- `step_optimizer.optimize()`（ILP求解）
- 状態更新 `prev_freq = curr_freq` / `current_mvs = next_mvs`（`curr_freq` 未定義によるエラー回避のためガード必須）

**保持**（全タイムステップ）:
- `z_by_timestep` の記録（T件）
- `migration_analysis` の記録（T件、各時刻の構成と移行）
- 最終ステップの `solve_time_sec` は `0.0`

### 3.4 修正による差分

| 項目 | 旧 | 新 |
|------|-----|-----|
| MV構成・移行・ベンチマーク | — | **変化なし** |
| `step_solve_times_sec` 件数 | T | **T-1** |
| 最終ステップ `solve_time_sec` | 無駄な最適化時間 | **0.0** |
| `total_optimization_time_sec` / `avg_step_time_sec` | 1回分過大 | **正味の値に修正** |

→ MV選択・ベンチマークに影響なし。**最適化時間の集計が正確になる改善**。過去結果との時間比較の一貫性が必要なら、旧結果を補正するか再実行で揃える。

---

## 4. 最適化時間の集計について（確認事項）

`total_optimization_time_sec` は**初期MV決定の時間を含む**：

```python
total_optimization_time = initial_solve_time + sum(step_solve_times)
```

| フィールド | 内容 |
|-----------|------|
| `initial_solve_time_sec` | 初期MV決定（案B）の最適化時間 |
| `step_solve_times_sec` | 各ステップ（T-1件）の最適化時間 |
| `total_optimization_time_sec` | 初期 + 全ステップ |
| `phase_time_sec` | フェーズ全体の壁時計時間 |

**手法間比較の注意**: Adaptive/Peloton は「初期 + 各ステップ」、Dynamic は「全期間ILP 1回」と非対称。`initial_solve_time_sec` は別フィールドで保存済みのため、「初期含む / 除く」は事後に切り分け可能。

---

## 5. TwoStep の prev_freq（1つ目の頻度）は結果に無関係（確認事項）

`TwoStepOptimizer` は2時刻分の頻度（`prev_freq`, `curr_freq`）を受け取るが、**t=0 の `z` を固定しているため `prev_freq` は `next_mvs`（`selected_mvs_t1`）に一切影響しない**。

理由:
1. 目的関数の t=0 項 `Σ -u_ij·prev_freq[i]·y[i,j,0]` は固定 `z[j,0]` 下で `y[i,j,0]` を最適化するだけ → **定数オフセット**。
2. t=0 と t=1 を結ぶのは `c[j,1] = max(0, z[j,1] − z[j,0])` のみだが `z[j,0]` は定数 → `c[j,1]` は `z[j,1]` だけで決まる。
3. `y[i,j,0]` は t=1 のどの制約にも現れない（y≤z・重なり排除・ストレージは各t独立）。

さらにループでは `selected_mvs_t1` のみ使用し目的関数値は破棄するため、`prev_freq` は完全に無関係。

**現在の入力値**（無害だが記録）:
- 初期MV / 各ステップ t=0: `initial_freq`
- 各ステップ t≥1: 前イテレーションの `curr_freq`

→ 現状維持で計算結果・ベンチマークに影響なし。

---

## 付録：変更ファイル一覧

| ファイル | 変更 |
|----------|------|
| `scripts/run_experiment_normal.py` | Peloton モード追加（phase6 routing / phase6c lookahead / phase7・8・9 分岐 / argparse）、最終ステップ最適化スキップ |

### 手法対応表（最終形）

| `--optimization-mode` | 説明 | 結果ファイル |
|----------------------|------|-------------|
| `static` (+`--static-algorithm bigsubs`) | 静的一括 | `static_bigsubs_optimization_result{suffix}.json` |
| `adaptive` (`--window-size`, `--freq-weight`) | 過去移動平均・反応型 | `adaptive_mv_optimization_result_w{W}{suffix}.json` |
| `peloton` | 1ステップ先読み・完全予知 | `peloton_mv_optimization_result{suffix}.json` |
| `dynamic` (`--use-pruning`) | 全期間一括 | `td_mv_optimization_result{suffix}.json` |
