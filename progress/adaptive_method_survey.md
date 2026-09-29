# Adaptive最適化手法の模倣妥当性 調査レポート

- **対象**: `scripts/run_experiment_normal.py` の `phase6c_optimize_adaptive` / `core/two_step_optimizer.py`
- **作成日**: 2026-06-18
- **調査対象論文**: CONST (2021), DeepSea (EDBT 2017) ＋ 代替候補

---

## 1. 結論サマリ

> **核心**
>
> 現在のAdaptive実装は、**CONST・DeepSea のいずれとも「重要な機構の次元」では一致していません**。ただし「過去ワークロードに反応して構成を逐次再最適化する」という**大枠の思想は両者と共有**しています。むしろ現在の実装は **CONSTより高機能**（CONSTは移行コストを無視・反応型なのに対し、本実装は移行コストを考慮・移動平均で予測）で、**DeepSeaとは目的関数の構造は一致するが解法（ILP vs 貪欲ヒューリスティック）と粒度が異なります**。

「代表的な適応手法を模倣する」という目的に対しては、実装の**機構（スライディングウィンドウ＋逐次再最適化＋移行コスト考慮＋近視眼的）**に最も近い代表論文は、CONST/DeepSeaよりも以下の3本です。

| 順位 | 論文 | 本実装との一致軸 | 総合一致度 |
|------|------|------------------|------------|
| 1 | **DynaMat** (Kotidis & Roussopoulos, SIGMOD 1999) | MV対象・構築コスト vs 便益・継続的再最適化 | **Strong** |
| 2 | **Bruno & Chaudhuri** "Online Approach to Physical Design Tuning" (ICDE 2007) | 近視眼的・「将来便益 > 構築コストなら作る」逐次再構成 | **Strong** |
| 3 | **COLT** (Schnaitter et al., SIGMOD 2006 demo / ICDE-W 2007) | スライディングウィンドウ(epoch)＋ステップ毎の貪欲再最適化 | **Strong** |

> ⚠️ **引用上の注意（重要）**
>
> - **DeepSea の著者が誤り**: ご提示の「J. Du, B. Glavic, and G. Agrawal」は不正確です。実際の著者は **J. Du, B. Glavic, W. Tan, R. J. Miller**（EDBT 2017）。Agrawal は参考文献に出てくるだけで著者ではありません。
> - **CONST に最も近い後続研究**として、NoSE の著者 Mior らの *"NoSQL Schema Design for Time-Dependent Workloads"* (arXiv:2303.16577) があります。これは**時間依存ワークロードに移行コストを組み込んだ時系列ILP**で、まさに本研究と同じ方向性。CONSTが移行コストを無視している点を明示的に批判して拡張しており、本実装の最も近い「思想的先行研究」です。

---

## 2. 現在のAdaptive実装の特性

`phase6c_optimize_adaptive` と `TwoStepOptimizer` を読んだ結果、本実装は次の機構を持ちます。

### 処理フロー

```
初期MV: TimeDependentOptimizer（1ステップ, migration_cost=0 で純ワークロード最適）
   ↓
各タイムステップ t = 0..T-1:
   ① 現在のMV構成を記録
   ② 過去 W 時刻の頻度の単純移動平均を curr_freq とする（スライディングウィンドウ予測）
   ③ TwoStepOptimizer を解く:
        t=0: z を current_mvs に固定
        t=1: z を最適化
        目的: minimize  Σ_t Σ_ij -u_ij·freq_t[i]·y_ij      (ワークロード実行コスト)
                       + w · Σ_j cost_j · c[j,1]            (新規MVの構築=移行コスト)
   ④ current_mvs ← selected_mvs_t1（1ステップだけ先を見て更新）
```

### 本質的な性質

| 軸 | 本実装の挙動 |
|----|--------------|
| 最適化単位 | 2タイムステップ局所ILP（現在固定・次を最適化）を T 回 |
| 視野 | **近視眼的（1ステップ先読み）** |
| ワークロード予測 | **直近 W 時刻の単純移動平均**（軽量な予測） |
| 移行/構築コスト | **考慮あり**（新規作成MVの `cost_j` を目的関数に算入。削除コストは無し） |
| 解法 | 厳密ILP（Gurobi） |
| 対象 | マテリアライズドビュー（MV） |
| 再構成トリガ | 毎タイムステップ無条件（変化検知トリガは無い） |

---

## 3. CONST との照合

> M. Mozaffari, E. Nazemi, A.-M. Eftekhari-Moghadam. "CONST: Continuous online NoSQL schema tuning." *Softw. Pract. Exp.* 51(5):1147–1169, 2021.
> （本文はペイウォール。著者の先行論文・NoSE・第三者比較論文から再構成）

### CONST のアルゴリズム要点

- **[確認] 対象**: NoSQL（Cassandra）の列ファミリ＝非正規化クエリテーブルのスキーマ調整。MV選択そのものではなく非正規化テーブルの選択。
- **[確認] オンライン機構**: IBMの MAPE-K 自律制御ループ。オンラインK-meansでワークロードをクラスタリングし、**n-gramモデルのperplexity（困惑度）が閾値を超えたら「ワークロードが変化した」と判定して再構成をトリガ**。固定窓でも周期実行でもなく、**統計的変化検知トリガ**。
- **[確認] WHAT の決定**: NoSE由来のコストベース選択だが、連続実行のため**ヒューリスティック/逐次的にスキーマを変更**（フルBIPの再求解はしない）。
- **[確認] 移行コスト**: **考慮しない**。第三者（NoSE著者）が「CONSTはスキーマ変更時のDB移行コストを無視するため時間依存ワークロードでは最適でない」と明記。
- **[確認] 予測**: **反応型（予測しない）**。観測履歴からクラスタ/モデルを学習し変化を検知するのみ。

### 本実装 vs CONST

| 軸 | CONST | 本実装 | 一致 |
|----|-------|--------|------|
| 対象 | NoSQL列ファミリ | MV | ❌ 不一致 |
| 再構成トリガ | perplexity変化検知 | 毎ステップ無条件 | ❌ 不一致 |
| WHATの解法 | ヒューリスティック | 厳密ILP | ❌ 不一致 |
| 移行コスト | 無視 | 考慮あり | ❌ 逆（本実装の方が高機能） |
| 予測 | 反応型 | 移動平均で予測型 | ❌ 逆（本実装の方が高機能） |
| 大枠の思想 | 「ワークロードに応じて物理設計を継続的に再調整するオンライン手法」 | 同左 | ✅ 一致 |

> **評価: Weak**　機構レベルでは大半が不一致、しかも移行コスト・予測の2軸では**本実装の方がCONSTより進んでいる**。「CONSTを模倣した」と述べるのは正確ではなく、むしろ「CONSTの弱点（移行コスト無視・反応型）を補う方向」に位置する。

---

## 4. DeepSea との照合

> J. Du, B. Glavic, W. Tan, R. J. Miller. "DeepSea: Progressive Workload-Aware Partitioning of Materialized Views in Scalable Data Analytics." *EDBT 2017*, pp. 198–209.（全文取得済み）

### DeepSea のアルゴリズム要点

- **[確認] 対象**: **MV選択と水平パーティショニングの同時最適化**。MV選択も含む。中間結果（join/agg/proj）をビュー候補とし、選択属性でフラグメントに分割。フラグメントは**重複を許す**（再分割コスト削減の要）。
- **[確認] "Progressive"**: **クエリ1件ごとにオンライン**で構成を逐次精緻化。固定窓や周期実行は無く、各クエリがコスト便益フィルタを通れば再分割。適応は**時間減衰関数 DEC**で実現（直近の便益を重視）。
- **[確認] 決定アルゴリズム**: **貪欲＋コスト便益比 Φ のナップサック型ヒューリスティック**。**ILP/最適/競合アルゴリズムは「非現実的」として明示的に却下**。
- **[確認] 目的関数 (Def. 4)**:

  ```
  COST(Q,C) = Σ_i COST(Q_i, C_i)  +  Σ_i COST(C_i, C_{i+1})
              └ クエリ実行コスト ┘    └ 構成間の移行コスト ┘
     s.t.  C_1 = ∅,  S(C_i) ≤ S_max
  ```

  → この「実行コスト＋移行コストの系列和を予算下で最小化」という形は、本実装のスライディングウィンドウILPの目的と**構造的に一致**。ただしDeepSeaはこれをILPで解かない。
- **[確認] 移行コスト**: 明示的にモデル化。フラグメント作成コスト `COST(I) = w_write·S(I) + Σ w_read·S(重複フラグメント)` を `便益≥コスト` フィルタで判定。
- **[確認] 予測**: 主に反応型（減衰履歴）だが、**正規分布をMLEで当てはめる予測サブモデル**でホットスポット近傍のフラグメント将来アクセスを予測。

### 本実装 vs DeepSea

| 軸 | DeepSea | 本実装 | 一致 |
|----|---------|--------|------|
| 目的関数の構造 | 実行コスト＋移行コストの系列和 | 同左（2ステップ窓） | ✅ 一致 |
| 移行コスト考慮 | あり（便益≥コストフィルタ） | あり（目的関数に算入） | ✅ 一致 |
| 対象 | MV＋パーティション | MV | 🔶 部分一致 |
| 視野/逐次性 | クエリ毎に近視眼的 | タイムステップ毎に近視眼的 | 🔶 部分一致 |
| 解法 | 貪欲Φ比ヒューリスティック | 厳密ILP | ❌ 不一致 |
| 粒度 | フラグメント（ビュー部分範囲） | MV全体 | ❌ 不一致 |
| 予測 | 減衰履歴＋MLE正規分布 | 単純移動平均 | 🔶 部分一致（両者とも履歴ベース） |

> **評価: Moderate**　**目的関数の構造（実行＋移行コストの系列最小化）と移行コスト考慮はよく一致**するが、DeepSeaは「ILPを明示的に却下した貪欲ヒューリスティック」「フラグメント粒度」である点で機構が異なる。本実装はDeepSeaの**目的（Def.4）をILPで素直に解いた版**と言える（DeepSea自身は解いていない定式化）。

---

## 5. より相応しい代表論文の候補

本実装の機構（**スライディングウィンドウ予測 ＋ 移行コスト付き逐次再最適化 ＋ 近視眼的**）を「代表的な適応手法の模倣」として位置づけるなら、以下が CONST/DeepSea より適切です。

### ① DynaMat — **Strong**（MV側の最有力）

> Y. Kotidis, N. Roussopoulos. "DynaMat: A Dynamic View Management System for Data Warehouses." *SIGMOD 1999* / 拡張版 TODS 2001.

- MVを**動的プール（キャッシュ的）**として管理。クエリ毎に「プールから答えるか」「新結果を採用するか」を判断。
- 選択と保守を単一の **"goodness"指標**（頻度・サイズ・recency・(再)計算/更新コスト）に統合し、構築コスト vs 便益を中心に据える。
- **MVを対象**・**近視眼的貪欲**・**構築コスト考慮**の3点で本実装に最も多く一致。差分は「キャッシュ的ヒューリスティック vs ILP」「recency減衰 vs 明示的移動平均窓」。

### ② Bruno & Chaudhuri — **Strong**（「便益＞構築コストなら作る」の規範）

> N. Bruno, S. Chaudhuri. "An Online Approach to Physical Design Tuning." *ICDE 2007*, pp. 826–835.

- 常時稼働でワークロード変化に反応し、構造を逐次作成/削除。
- **「将来のある時点での便益が構築コストを上回るなら作る」**という規則を明示。これは本実装の便益 vs 構築コストのトレードオフそのもの。
- 近視眼的・反応型・逐次調整も一致。差分は「インデックス対象」「ILPでない」。

### ③ COLT — **Strong**（スライディングウィンドウ＋ステップ毎再最適化）

> K. Schnaitter, S. Abiteboul, T. Milo, N. Polyzotis. "COLT: Continuous On-Line Tuning." *SIGMOD 2006 (demo)* ／ "On-Line Index Selection for Shifting Workloads," *ICDE Workshops (SMDB) 2007*.
> ※ ご認識の「COLT SIGMOD 2007」は誤り。正しくは SIGMOD 2006 demo ＋ ICDE-W 2007。

- クエリストリームを**長さ w のepoch（＝スライディングウィンドウ）**に分割し、直近epochの平均で便益推定（＝移動平均予測）。
- epoch毎に予算下で**貪欲に再選択**。本実装の「窓予測→ステップ毎再最適化」ループと最も直接的に対応。
- 差分は「インデックス対象」「構築コストは別スケジューラ」「ILPでない」。

### ④ Weisgut & Schlosser — **Moderate〜Strong**（移行コスト付き多期間MILPの最近接）

> M. Weisgut, L. Hübscher, O. Nordemann, R. Schlosser. "Solver-Based Approaches for Robust Multi-Index Selection Problems with Reconfiguration Costs under Stochastic Dynamic Workloads." *ICORES 2022* ／ 拡張 SN Comp. Sci. 2023.

- **MILP（ソルバーベース）で構成間の再構成コストを明示的に課す**動的ワークロード向け定式化。本実装の移行コスト付きILPに構造的に最も近い。
- 差分は「インデックス対象」「ロバスト/多シナリオ（近視眼的単一予測ではない）」。

### 補足: 思想的に最も近い後続研究

> **Mior et al. "NoSQL Schema Design for Time-Dependent Workloads" (arXiv:2303.16577, 2023)**
>
> CONSTが移行コストを無視する点を明示的に問題視し、**時間依存ワークロードに移行コストを組み込んだ時系列ILP**を提案。これは本研究（時間依存MV＋移行コストILP）と**同じ問題設定・同じ動機**であり、関連研究として必ず押さえるべき。本実装のDynamic/Adaptiveはこの系譜に位置づけるのが自然。

---

## 6. 推奨と論文での位置づけ方

> **推奨する記述方針**
>
> 1. **「CONST/DeepSeaを忠実に再現した」とは書かない**。機構が異なり、特にCONST比では本実装の方が高機能なため、誤解を招く。
> 2. **Adaptive手法は「オンライン/適応型物理設計チューニングの代表的クラスを模倣した比較ベースライン」**と位置づける。具体的には「直近ワークロードの移動平均で近未来を予測し、移行コストを考慮しつつ近視眼的に構成を逐次再最適化する」手法、と機構で定義する。
> 3. その代表として **COLT（窓＋逐次再最適化）・Bruno&Chaudhuri（便益>構築コストで作る近視眼的調整）・DynaMat（適応的MV管理＋構築コスト）** を引用。CONST・DeepSea も「適応型物理設計の関連研究」として引けるが、模倣元というより**同じ問題意識の関連研究**として扱う。
> 4. 静的手法（BigSubs）の忠実な再現と対比させ、**「静的＝BigSubsを忠実再現／動的＝代表的オンライン手法群の機構を統合したベースライン」**という非対称性を正直に明記する。これは査読でも防御しやすい。

### 本実装の機構的立ち位置（1文要約）

本実装のAdaptiveは、**COLTのスライディングウィンドウ逐次再最適化**＋**Bruno&Chaudhuri/DynaMatの「構築コスト vs 便益」近視眼的判断**を、**DeepSea(Def.4)型の実行＋移行コスト目的関数**として**厳密ILPで解いた合成手法**である、と表現するのが最も正確。

> ⚠️ **付随する既知の課題（別途指摘済み）**
>
> 初期MVを `migration_cost=0` の別Optimizer（`TimeDependentOptimizer`）で算出しているため、頻度変化が無くても初期MV→次MVでMV数が減る現象が起きる。これは「適応手法の模倣」とは独立の**定式化の不整合バグ**であり、初期MVも `TwoStepOptimizer` で（または収束反復で）求めて定式化を統一すべき。模倣妥当性の議論とは切り分けて扱うのがよい。

---

## 7. 参考文献

1. M. Mozaffari, E. Nazemi, A.-M. Eftekhari-Moghadam. "CONST: Continuous online NoSQL schema tuning." *Software: Practice and Experience* 51(5):1147–1169, 2021. DOI 10.1002/spe.2945.
2. J. Du, B. Glavic, W. Tan, R. J. Miller. "DeepSea: Progressive Workload-Aware Partitioning of Materialized Views in Scalable Data Analytics." *EDBT 2017*, pp. 198–209.（openproceedings.org/2017/conf/edbt/paper-20.pdf）
3. Y. Kotidis, N. Roussopoulos. "DynaMat: A Dynamic View Management System for Data Warehouses." *SIGMOD 1999*, pp. 371–382. ／ "A Case for Dynamic View Management." *ACM TODS* 26(4), 2001.
4. N. Bruno, S. Chaudhuri. "An Online Approach to Physical Design Tuning." *ICDE 2007*, pp. 826–835.
5. K. Schnaitter, S. Abiteboul, T. Milo, N. Polyzotis. "COLT: Continuous On-Line Tuning." *SIGMOD 2006* (demo), pp. 793–795. ／ "On-Line Index Selection for Shifting Workloads." *ICDE Workshops (SMDB) 2007*, pp. 459–468.
6. K. Schnaitter, N. Polyzotis. "Semi-Automatic Index Tuning: Keeping DBAs in the Loop." *PVLDB* 5(5):478–489, 2012.
7. M. Weisgut, L. Hübscher, O. Nordemann, R. Schlosser. "Solver-Based Approaches for Robust Multi-Index Selection Problems with Reconfiguration Costs under Stochastic Dynamic Workloads." *ICORES 2022*, pp. 28–39. ／ R. Schlosser et al. "Robust Index Selection for Stochastic Dynamic Workloads." *SN Computer Science* 4:59, 2023.
8. Mior et al. "NoSQL Schema Design for Time-Dependent Workloads." arXiv:2303.16577, 2023.
9. A. Jindal, K. Karanasos, S. Rao, H. Patel. "Selecting Subexpressions to Materialize at Datacenter Scale." *PVLDB* 11(7):800–812, 2018.（BigSubs／静的手法の比較元）
10. L. Ma et al. "Query-based Workload Forecasting for Self-Driving Database Management Systems (QueryBot 5000)." *SIGMOD 2018*.（予測層の参考）

---

*凡例: [確認]＝一次/権威ある情報源で確認済み、[推定]＝周辺情報からの推定。*
*CONSTは本文ペイウォールのため、著者の先行論文（Tabriz J. 2019, Algorithm 1–3）・NoSE (TKDE 2017) のコストモデル・arXiv:2303.16577 の第三者評価から再構成した。DeepSeaは全文を取得して確認した。*
