ワークスペース情報を収集しています以下の方針で「時刻変化＋マイグレーションコスト」を含むILP最適化を実装すると安全かつ拡張しやすいです。既存のILP（単一時刻）を壊さず、別クラスとして追加します。

要点
- 目的は最小化: 各時刻のワークロード実行コスト（＝現行の利得 u_ij の負符号）＋マイグレーションコスト
- 変数と制約は時刻tで拡張: y[i,j,t], z[j,t] に加え、作成フラグ c[j,t] とレシピ選択 a[j,t,K]
- migration_costs.json は「ある時刻t−1に存在するMV集合から、時刻tにMV j を作るときの最小作成コスト」をレシピで表現していると解釈
- 削除コストは0（ファイルに無いため）としてモデル化
- m_cost（メンテナンスコスト）は無視（0）

数式（KaTeX）
- 変数:
  - $y_{i,j,t} \in \{0,1\}$: クエリiが時刻tでMV jを使う
  - $z_{j,t} \in \{0,1\}$: MV jが時刻tで存在
  - $c_{j,t} \in \{0,1\}$: MV jが時刻tで新規作成（t>0）
  - $a_{j,t,K} \in \{0,1\}$: レシピKでMV jを作成（t>0）
- 制約:
  - 重複・包含（既存と同じ）: $y_{i,j,t} + \frac{1}{|J|}\sum_{u\in J} X_{j,u} \, y_{i,u,t} \le 1$
  - 利用は実体化に従属: $y_{i,j,t} \le z_{j,t}$
  - ストレージ制約: $\sum_j b_j z_{j,t} \le B_{\max}$
  - 作成フラグ定義: $c_{j,t} \ge z_{j,t} - z_{j,t-1}$, $c_{j,t} \le z_{j,t}$（t>0）
  - レシピ選択: $\sum_K a_{j,t,K} = c_{j,t}$, $a_{j,t,K} \le z_{m,t-1}$（全ての m∈K）, $a_{j,t,K} \le c_{j,t}$
- 目的関数（最小化）:
  - ワークロード: $-\sum_t \sum_i \sum_j f_{i,t}\, u_{i,j}\, y_{i,j,t}$
  - マイグレーション: $\sum_{t>0}\sum_j\sum_K \text{cost}_{j,K}\, a_{j,t,K}$

実装ステップ
1) 新しいオプティマイザを追加
- Baseは現行の単一時刻用のため、時間軸を持つ専用クラスを作成（既存を変更しない）
- 参考: 時系列の試作は time_depend_ilp.py

2) migration_costs.json を読み込み
- キーが "['leaf_3','non_leaf_4']" のような文字列なので ast.literal_eval で配列化
- すべての j について K∈レシピ毎のコストを辞書化
- K=[] は「前時刻から何も使わずに作成（フル作成）」のフォールバック

3) ILPを時刻tで拡張
- y[i,j,t], z[j,t], c[j,t], a[j,t,K] を追加
- 制約は上記の式に従って各 t に張る
- 目的関数は最小化（利得に負符号＋マイグレーションコスト）

4) 出力
- 各時刻 t の z[j,t] を返す（metadataに z_by_timestep を格納）
- 後段のリライト・SQL生成は時刻ごとに呼ぶ（現行の単一時刻と両立させる）

提案コード
- 新規 Optimizer を追加します（最小限の骨格）。頻度 f_{i,t} を与えない場合は 1 を用います。

````python
# ...existing code...
import json
import ast
import logging
from typing import Dict, List, Tuple

import gurobipy as gp

from .base import BaseILPOptimizer
from ..core.models import OptimizationResult

logger = logging.getLogger(__name__)

class TimeDependentOptimizer:
    """
    時刻変化ワークロード＋マイグレーションコスト対応ILP

    注意:
      - BaseILPOptimizerを直接継承せず、時間軸の都合で専用に実装
      - 目的関数は最小化: -(利得) + マイグレーション作成コスト
      - 削除コストは0（migration_costs.jsonに無いため）
    """

    def __init__(
        self,
        base: BaseILPOptimizer,  # 既存のデータ構造を再利用（qm, u_ij, X, b_j, B_max など）
        timesteps: List[str],
        migration_costs_path: str,
        query_frequency_by_timestep: Dict[str, List[float]] | None = None,
    ):
        self.base = base
        self.qm = base.qm
        self.u_ij = base.u_ij
        self.X = base.X
        self.b_j = base.b_j
        self.B_max = base.B_max
        self.node_list = base.node_list

        self.timesteps = timesteps
        self.freq = query_frequency_by_timestep or {
            t: [1.0] * len(self.u_ij) for t in timesteps
        }

        with open(migration_costs_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        self.mig_costs = self._parse_migration_costs(raw)

        self.model: gp.Model | None = None

    def _parse_migration_costs(self, raw: dict) -> Dict[int, List[Tuple[Tuple[int, ...], float]]]:
        """JSONを {j_index: [ (recipe_tuple_of_indices, cost), ... ]} に変換"""
        idx = {node_id: j for j, node_id in enumerate(self.node_list)}
        mig: Dict[int, List[Tuple[Tuple[int, ...], float]]] = {}
        for node_id, mapping in raw.items():
            j = idx.get(node_id)
            if j is None:
                continue
            recipes: List[Tuple[Tuple[int, ...], float]] = []
            for k_str, cost in mapping.items():
                # k_str: "[]", "['leaf_3']", "['leaf_3','non_leaf_4']" ...
                try:
                    ids = ast.literal_eval(k_str)
                    if not isinstance(ids, list):
                        ids = []
                except Exception:
                    ids = []
                recipe = tuple(sorted(idx[i] for i in ids if i in idx))
                recipes.append((recipe, float(cost)))
            # レシピが無いときのフォールバック
            if not any(len(r[0]) == 0 for r in recipes):
                recipes.append((tuple(), float("inf")))
            mig[j] = recipes
        return mig

    def optimize(self) -> OptimizationResult:
        T = len(self.timesteps)
        I = len(self.u_ij)
        J = len(self.b_j)

        m = gp.Model("TimeDependentMV")
        m.Params.OutputFlag = 0

        # 変数
        y = {}  # y[i,j,t]
        z = {}  # z[j,t]
        c = {}  # c[j,t], t>=1のみ実質使用
        a = {}  # a[j,t,K_idx]

        # y, z
        for t in range(T):
            for j in range(J):
                z[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}_{t}")
            for i in range(I):
                for j in range(J):
                    y[i, j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}_{t}")

        # c, a
        for t in range(1, T):
            for j in range(J):
                c[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"c_{j}_{t}")
                # レシピごとに a を用意
                recs = self.mig_costs.get(j, [(tuple(), 0.0)])
                for k_idx, (recipe, _) in enumerate(recs):
                    a[j, t, k_idx] = m.addVar(vtype=gp.GRB.BINARY, name=f"a_{j}_{t}_{k_idx}")

        m.update()

        # 制約: 重複/包含 + 利用は実体化に従属 + ストレージ
        for t in range(T):
            # 重複/包含（Baseと同型）
            for i in range(I):
                for j in range(J):
                    m.addConstr(
                        y[i, j, t]
                        + gp.quicksum(y[i, u, t] * self.X[j][u] for u in range(J)) / J
                        <= 1,
                        name=f"overlap_{i}_{j}_{t}",
                    )
                    m.addConstr(y[i, j, t] <= z[j, t], name=f"use_le_materialize_{i}_{j}_{t}")

            # ストレージ
            m.addConstr(
                gp.quicksum(self.b_j[j] * z[j, t] for j in range(J)) <= self.B_max,
                name=f"storage_{t}",
            )

        # 制約: 作成フラグ c と レシピ選択 a（t>=1）
        for t in range(1, T):
            for j in range(J):
                # c >= z_t - z_{t-1}, c <= z_t
                m.addConstr(c[j, t] >= z[j, t] - z[j, t - 1], name=f"create_lb_{j}_{t}")
                m.addConstr(c[j, t] <= z[j, t], name=f"create_ub_{j}_{t}")

                recs = self.mig_costs.get(j, [(tuple(), 0.0)])
                # レシピ選択はちょうど1つ: sum a == c
                m.addConstr(
                    gp.quicksum(a[j, t, k_idx] for k_idx in range(len(recs))) == c[j, t],
                    name=f"recipe_pick_{j}_{t}",
                )
                # レシピの前提: a[j,t,K] <= z[m,t-1] for all m in K, and a <= c
                for k_idx, (recipe, _) in enumerate(recs):
                    m.addConstr(a[j, t, k_idx] <= c[j, t], name=f"recipe_coupling_{j}_{t}_{k_idx}")
                    for m_dep in recipe:
                        m.addConstr(
                            a[j, t, k_idx] <= z[m_dep, t - 1],
                            name=f"recipe_dep_{j}_{t}_{k_idx}_{m_dep}",
                        )

        # 目的関数: 最小化
        # 1) ワークロードコスト = -(利得)（頻度で重み付け）
        workload_cost = gp.quicksum(
            -self.u_ij[i][j] * self._freq(t_idx=self.timesteps[t], i=i) * y[i, j, t]
            for t in range(T)
            for i in range(I)
            for j in range(J)
        )

        # 2) マイグレーションコスト = 作成時のレシピ費用
        migration_cost = gp.quicksum(
            self.mig_costs.get(j, [(tuple(), 0.0)])[k_idx][1] * a[j, t, k_idx]
            for t in range(1, T)
            for j in range(J)
            for k_idx in range(len(self.mig_costs.get(j, [(tuple(), 0.0)])))
        )

        m.setObjective(workload_cost + migration_cost, gp.GRB.MINIMIZE)
        m.optimize()

        # 解の抽出
        z_by_t = []
        for t in range(T):
            z_t = [int(z[j, t].X) for j in range(J)]
            z_by_t.append(z_t)

        # 最終タイムステップの出力を従来と同じ構造にしつつ、全時刻の情報をmetadataに格納
        final_z = z_by_t[-1]
        selected_idx = [j for j, v in enumerate(final_z) if v == 1]
        y_dummy = [[0] * J for _ in range(I)]  # 単一時刻用との互換目的のダミー
        result = self.base.create_result(
            y_ij=y_dummy,
            z_j=final_z,
            obj_val=m.objVal,
            execution_time=0.0,
            generate_sql=False,
            z_by_timestep=z_by_t,
            timesteps=self.timesteps,
        )
        return result

    def _freq(self, t_idx: str, i: int) -> float:
        return float(self.freq.get(t_idx, [1.0] * len(self.u_ij))[i])
# ...existing code...
````

統合ポイント
- Factoryに登録（アルゴリズム名 time_dependent など）
- 実行スクリプトで timesteps, migration_costs.json パス、（任意で）時刻別頻度を渡す

````python
# ...existing code...
from .time_dependent import TimeDependentOptimizer

class OptimizerFactory:
    # ...existing code...
    @classmethod
    def create(cls, algorithm: str, **kwargs):
        # ...existing code...
        if algorithm == "time_dependent":
            base = kwargs["base"]  # BaseILPOptimizer インスタンス
            timesteps = kwargs["timesteps"]
            mig_path = kwargs["migration_costs_path"]
            freq = kwargs.get("query_frequency_by_timestep")
            return TimeDependentOptimizer(base, timesteps, mig_path, freq)
        # ...existing code...
````

呼び出し例（擬似）
- 既存の単一時刻オプティマイザ（例: normal.py の `NormalOptimizer`）を初期化し、それを base として渡すと、内部の `qm, u_ij, X, b_j, B_max, node_list` を流用できます。

- scripts 側で:
  - timesteps = ["morning","evening"]
  - migration_costs_path = "experiments/small_test_ver2/time_dependent_output/migration_plan/migration_costs.json"
  - query_frequency_by_timestep は無ければ省略（=1.0）

注意点・補足
- レシピの組合せが多いと変数が増えます。migration_costs.json のキー数が大きい場合は、K のサイズ（len(K)）で上限を設けるなどの枝刈りを検討
- 削除コストが必要になったら、d[j,t] >= z[j,t-1] - z[j,t] を導入し、削除レシピ（存在するなら）も同様に a^- を定義
- 初期時刻 t=0 の作成コストは、前時刻が無いので K=[] のレシピのみ許可し、c[j,0]=z[j,0] として同様に目的に入れることも可能（今回は簡略のため除外）
- 既存の実装との関係は、単一時刻のILP（base.py）の重複・包含・ストレージ制約を各時刻に展開しただけ。試作参考: time_depend_ilp.py

この形にしておけば、後から「更新コスト（m_cost）」や「MV作成SQL・書き換え」を時刻ごとに拡張しやすいです。