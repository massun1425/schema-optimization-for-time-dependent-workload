# BigSubs / Adaptive 最適化の論文整合化・変更まとめ

- **日付**: 2026-06-18
- **対象**: `src/optimization/bigsubs.py`, `core/two_step_optimizer.py`, `scripts/run_experiment_normal.py`
- **目的**: 静的手法（BigSubs）を論文に忠実化し、動的比較手法（Adaptive）を既存のオンライン物理設計手法の代表として整合的に再構成する

> 関連: 動的手法の模倣妥当性の調査は [`adaptive_method_survey.md`](adaptive_method_survey.md) を参照。

---

## 0. 全体像：手法の位置づけ

本研究の比較手法は「静的 vs 動的」の軸で構成される。

| 手法 | 役割 | 元になる既存研究 |
|------|------|-----------------|
| No MV | 下界 | — |
| **Static (BigSubs)** | 時間変化を無視した一括選択 | BigSubs (VLDB 2018) を**忠実再現** |
| **Adaptive** | 近視眼的に変化追従するオンライン手法 | DeepSea / COLT / DynaMat / Bruno&Chaudhuri の**機構を統合した代表ベースライン** |
| **Dynamic** | 全期間を見通した移行コスト付き時系列最適化（提案） | 時間依存ワークロード＋移行コストILP（arXiv:2303.16577 の系譜） |

今回の変更は (A) BigSubs の論文忠実化、(B) Adaptive の便益モデルを Dynamic と統一、(C) Adaptive の初期化整合化、(D) ウィンドウ重み付けの線形減衰化、の4本柱。

---

## 1. 既存手法の説明

### 1.1 BigSubs（静的手法の元）

> A. Jindal, K. Karanasos, S. Rao, H. Patel. "Selecting Subexpressions to Materialize at Datacenter Scale." *PVLDB* 11(7):800–812, 2018.

データセンタ規模で、クエリプランの**部分式（subexpression）**をマテリアライズ対象候補とし、ストレージ予算下で全クエリの総効用を最大化する選択問題。完全なILPは大規模で解けないため、**二部グラフ上のラベリング問題**に変換し以下を反復する近似アルゴリズム（Algorithm 1）：

1. **Vertex labeling**: 各部分式 `z_j∈{0,1}`（materializeするか）を**確率的に反転**（フリップ）。容量項 `p_capacity` × 効用項 `p_utility` の積で反転確率を決める。
2. **Edge labeling**: 各クエリごとに小さな**ローカルILP**を解き、どの部分式を使うか `y_ij` を決定。

- 目的関数（ローカルILP, Eq.6）: `maximize Σ_j u_ij · y_ij`
- 反転確率の効用項（未materialize時）: `(U^j_max / b_j) / (U_max / B_max)`
- `U_max = Σ_{i,j} u_ij`, `U^j_max = Σ_i u_ij` を**初期化時に計算**
- 終了条件: `while (updated OR iter < k)`（更新が無く、かつ最大反復に達したら停止）

**スケール不変性**: 効用 `u_ij` を一律スケールしても `U^j_max/U_max` の比が不変なため反転確率もローカルILP解も変わらない（average と sum で結果が同一）。

### 1.2 動的に変化追従するオンライン手法のクラス

Adaptive が代表しようとする手法群。共通点は「**近視眼的・直近ワークロードに反応・移行/構築コスト考慮・現構成からの増分調整**」。

- **DeepSea** (Du, Glavic, Tan, Miller, EDBT 2017): MV選択＋水平パーティショニングをクエリ毎にオンライン精緻化。目的関数 `Σ COST(Q_i,C_i) + Σ COST(C_i,C_{i+1})`（実行コスト＋移行コスト）。貪欲＋コスト便益比ヒューリスティック（ILPは非現実的として却下）。**時間減衰 DEC = t/t_now**（線形）で直近を重視。
- **COLT** (Schnaitter et al., SIGMOD 2006 / ICDE-W 2007): クエリストリームを長さ w のエポックに分割し、直近エポックの**一様平均**で便益推定。エポック毎に貪欲再選択。
- **DynaMat** (Kotidis & Roussopoulos, SIGMOD 1999): MVを動的プールとして管理。"goodness"指標（頻度・サイズ・recency・再計算コスト）でadmission/eviction。
- **Bruno & Chaudhuri** (ICDE 2007): 常時稼働で「将来便益 > 構築コストなら作る」近視眼的逐次再構成。

> 重要: これらは**スケーラビリティのためヒューリスティックを使う**が、本研究では Adaptive を**ILP**で実装する。理由は「Dynamic との性能差が最適化視野（全期間 vs 近視眼的）に起因することを保証し、ソルバー近似による交絡を排除する」ため。これにより Adaptive は「近視眼的だが厳密」な、より強く公平なベースラインになる。

---

## 2. 変更点A：BigSubs を論文に忠実化（`src/optimization/bigsubs.py`）

論文 Algorithm 1 と現実装を照合し、以下を修正。

### A-1. 終了条件（最終結論: `and` のまま維持）
論文は擬似コードと自然言語説明で記述が食い違う（下記）。一度 `or` に変更したが、
非停止リスクを避けるため最終的に**安全な `and`（最大 iter_max 回・収束で早期終了）に戻した**。

```python
# 採用（= 元の実装と同じ）: 最大 iter_max 回、収束したら早期終了
while updated == 1 and iter_num < iter_max:
```

- **論文擬似コード**: `while (updated OR iter < k)` → 停止は「更新なし**かつ** iter≥k」。最低 k 回回し、その後は更新が止まるまで継続。iter_max を超え得るうえ、フリップが確率的に続くと**非停止リスク**。
- **論文の自然言語説明**: "loop runs until no label changes **or** iter reaches max" → 「収束**または**最大反復の早い方で停止」＝ `and` 相当。
- **判断**: 自然言語説明・一般的な実装慣習・安全性（停止保証）を優先し `and` を採用。`iter_max=200` で運用。実用上、予算飽和時 `p_capacity→0` で収束しやすいが、ハードに最大回数を保証する方が安全。

### A-2. フリップ確率しきい値 p の相対化
```python
# 修正前: 絶対値ハードコード（iter_max=50では一度も発動しない）
p = 160
# 修正後: iter_max の80%（論文デフォルト）。flip_probability に iter_max 引数を追加
p = int(0.8 * iter_max)
```

### A-3. ローカルILP目的関数から維持コストを除去
維持コストは本実装では不要との判断。論文 Eq.6 の純効用に戻す。
```python
# 修正前
gp.quicksum(u_ij_row[j] * y[j] - self.m_cost[j] * y[j] for j in k)
# 修正後
gp.quicksum(u_ij_row[j] * y[j] for j in k)
```
あわせて Edge labeling 後の `U_cur` 計算からも維持コスト項（`- m_cost/len`, `U_cur -= m_cost*z_j`）を除去し、論文通り「全クエリの効用合計」を積算。

### A-4. U_max / U^j_max を内部計算（バグ級の修正）
```python
# 修正前: 外部入力依存、未指定時は 0 → z_j=0 候補の追加確率が常に0になる致命的バグ
self.U_max = kwargs.pop("U_max", 0.0)
self.U_j_max = kwargs.pop("U_j_max", None)  # → [0]*s_num
# 修正後: u_ij から計算（論文 Algorithm 1 初期化）
self.U_j_max = [sum(self.u_ij[i][j] for i in range(len(self.u_ij))) for j in range(self.s_num)]
self.U_max = sum(self.U_j_max)
```

### A-5. ランダム初期化を独立ベルヌーイに
```python
# 修正前: 必ず1個以上選ぶ（分布が論文と異なる）
k = random.randint(1, len(mv_list)); k_list = random.sample(...)
# 修正後: 各MVを独立に0/1（論文の random labeling）
return [random.randint(0, 1) for _ in range(len(mv_list))]
```

### A-6. フリップ確率を [0,1] にクリップ
```python
# 修正後: utility密度比が1を超え得るため確率として正規化
return max(0.0, min(1.0, p_j_capacity * p_j_utility))
```

### A-7. Edge labeling 後の z_j 上書きを削除
論文 Algorithm 1 では Edge labeling は `y_ij, U_cur, U^j_cur` のみ更新し `z_j` は変えない。「実際に使われたMVだけ残す」改変を除去し、`z_j`/`B_cur` は Vertex labeling 側でのみ管理。

---

## 3. 変更点B：Adaptive の便益モデルを Dynamic と統一（`core/two_step_optimizer.py`）

### 背景の問題
`Dynamic = TimeDependentOptimizer` と `Adaptive = TwoStepOptimizer` で**便益モデルが食い違っていた**：

| | Dynamic | Adaptive（旧） |
|--|---------|---------------|
| 1クエリが使えるMV数 | 複数（重ならなければ便益合算） | **1個のみ**（`Σ_j y[i,j] ≤ 1`） |
| 重なり排除 | y レベル（クエリ単位） | z レベル（`z_j+z_u≤1`, 両方materialize不可） |

→ 同じ状況でも選ばれるMVが変わり、「Dynamic vs Adaptive の差＝最適化視野の差」という主張が**交絡**していた。

### B-1. 1クエリ1MV制約を削除
```python
# 削除: m.addConstr(gp.quicksum(sparse_ys) <= 1)
```
クエリは重ならない複数MVを使え、便益が合算される（Dynamic と一致）。

### B-2. 重なり排除を z レベル → y レベルに変更
```python
# 修正後（TimeDependent と同じ正規化 y レベル形式）
m.addConstr(
    y_var + gp.quicksum(
        self.y[i, u, t] * self.X[j][u]
        for u in self.pos_js_by_i.get(i, [])
        if u != j and self.X[j][u] != 0 and (i, u, t) in self.y
    ) / max(1, len(self.cand_j)) <= 1
)
```
意味: 包含関係にある2MVは**両方materialize可**だが、**1クエリが両方同時使用は不可**。重ならないMVは1クエリで同時使用でき便益合算。

### B-3. `fixed_mvs` の None / 空集合を区別（初期化のため）
```python
# 修正前: self.fixed_mvs = fixed_mvs or set()  # None も空集合も同じ → 空集合は固定されない罠
# 修正後:
self._t0_fixed = fixed_mvs is not None
self.fixed_mvs = fixed_mvs if fixed_mvs is not None else set()
```
- `None` → t=0 を自由に最適化
- `set()` → t=0 を**MVなしに固定**（build-from-empty 初期化用）
- `{..}` → t=0 を指定構成に固定（各ステップ用）

---

## 4. 変更点C：Adaptive 初期化を案Bに（`scripts/run_experiment_normal.py`）

### 背景の問題
旧実装は初期MVを `TimeDependentOptimizer` ＋ `migration_cost=0` で計算していた。
- 構築コストを無視して「便益>0」のMVを過剰選択
- → 頻度が変化していなくても次ステップで間引かれ、**初期MV→次MVでMV数が減る不整合**が発生

### C. 案B：空集合から実マイグレーションコストで構築
```python
initial_optimizer = TwoStepOptimizer(
    ...,
    prev_freq=initial_freq, curr_freq=initial_freq,
    migration_cost=migration_cost,   # 実コスト（0でない）
    fixed_mvs=set(),                 # t=0 を空に固定 → 満額構築コスト
)
current_mvs = set(initial_result["selected_mvs_t1"])
```

**なぜ直るか**: t=0 を空固定すると t=0 では y=0（便益0）、`c[j,1] ≥ z[j,1]` で**選んだMV全部に満額構築コスト**が課される。よって初期集合は `便益 − 構築コスト` を最大化する集合になり、各ステップの「便益 vs 構築コスト」判定（DeepSea/B&C の "create iff benefit > cost"）と**同じ論理**になる。頻度不変なら初期集合は各ステップ最適化の**不動点**になり、MV数が変動しない。

利点:
- 初期MVと各ステップが**同じ定式化・同じ便益モデル**
- 別オプティマイザ（`TimeDependentOptimizer`＋コスト0）が不要に
- 空固定の罠も B-3 で解消済み

---

## 5. 変更点D：ウィンドウ内頻度の重み付け（線形減衰）

### 背景
各ステップは過去 W 時刻の頻度を集約して `curr_freq` を作る。旧来は**単純移動平均（一様）**。DeepSea 等は直近を重視するため、線形 recency 重みを導入。

### D. `--freq-weight {uniform, linear}`
`freq_window` は古い→新しい順（index `k=W-1` が現在時刻）。
```python
if self.freq_weight == "linear":
    weights = [k + 1 for k in range(window_size)]   # 最古=1 ... 最新=W
else:  # uniform
    weights = [1 for _ in range(window_size)]
wsum = sum(weights)
curr_freq[i] = sum(weights[k] * freq_window[k][i] for k in range(window_size)) / wsum
```

| モード | 重み | 意味 |
|--------|------|------|
| `uniform`（デフォルト） | 1,1,…,1 | 単純移動平均（比較ベースライン） |
| `linear` | 1,2,…,W | DeepSea流の線形 recency 重み |

**正規化（`/wsum`）が必須**: BigSubs はスケール不変だが、**移行コスト vs 便益のトレードオフはスケール依存**（移行コストは絶対値）。重み和で割らないと W や重み形状を変えるたびに頻度総量が変わり、移行コストとの釣り合いがずれて純粋な予測効果を切り出せなくなる。

> **DeepSea原典との関係**: 厳密な `DEC = t/t_now` は絶対時刻依存（t が大きいほど減衰が平坦化）でウィンドウ方式では減衰形が時刻ごとに変わり交絡となる。`w_k = k+1` は**全時刻で一定形状の線形 recency 重み**で、「直近を線形に重視」という本質を保ちつつ実験的に扱いやすい。論文では「DeepSeaの線形recency重みに倣いウィンドウ内で一定形状の線形減衰を採用」と記述すれば妥当。
>
> 既存研究には**指数減衰αの具体値は存在しない**（DeepSea=線形 t/t_now で t_max値未公開、DynaMat=LRUタイムスタンプ、COLT=一様平均 w=10/h=12、QueryBot5000=等重み平均）。

---

## 6. パラメータ・使い方

```bash
# 静的（BigSubs）: 変更は内部のみ、呼び出しは従来通り

# Adaptive: 一様平均（基準）
python scripts/run_experiment_normal.py --phase 6 \
  --optimization-mode adaptive --window-size 4 ...

# Adaptive: DeepSea流 線形減衰
python scripts/run_experiment_normal.py --phase 6 \
  --optimization-mode adaptive --window-size 4 --freq-weight linear ...
```

主な新規/変更引数:
- `--freq-weight {uniform, linear}`（デフォルト `uniform`）

---

## 7. 残課題・要確認（Gurobi環境でのテスト）

本変更は構文チェックのみ実施。`gurobipy` 非搭載環境のため実行未確認。Docker/Gurobi 環境で以下を確認のこと:

1. **案Bの主目的**: 頻度不変ケースで初期MVと次MVが安定する（MV数が減らない）
2. **便益モデル統一**: Adaptive と Dynamic で極端な乖離が出ないか
3. **線形減衰**: `--freq-weight linear` で `peak` / `2_10` ワークロードの追従が改善するか
4. **BigSubs**: U_max内部計算により z_j=0 候補が正しく追加されるか（終了条件は `and` を維持したため反復は最大 iter_max で保証）,予算内で最良の解を出力する（論文ではここを強制していない）

### ロジック確認済みの点
- 案B: `fixed_mvs=set()` → t=0 で y全0・便益0、`c[j,1]≥z[j,1]` で満額構築コスト → 「便益−構築コスト最大化」
- B-3: 既存ループ呼び出し（非空 `current_mvs`）は `is not None` で挙動不変
- 線形/一様とも重み和で正規化しスケール保持

---

## 付録：変更ファイル一覧

| ファイル | 変更 |
|----------|------|
| `src/optimization/bigsubs.py` | A-1〜A-7（論文忠実化） |
| `core/two_step_optimizer.py` | B-1〜B-3（便益モデル統一・fixed_mvs区別） |
| `scripts/run_experiment_normal.py` | C（初期化案B）, D（`--freq-weight`） |
