import psycopg2
import re 
import json
import pickle
import sys
from pathlib import Path
from itertools import combinations
from typing import List, Dict, Any

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from config.settings import Settings
from experiments.small_test_ver2.frequency_weighted_parser import FrequencyWeightedParser
from experiments.small_test_ver2.simple_mv_sql_generator import SimpleMVSQLGenerator

class GetMigrationPlans:
    """MVのマイグレーションプランを取得"""
    def __init__(
            self,
            settings: Settings | None = None,
            parser_file: str | None = None,
    ):
        self.settings = settings
        self.parser_file = Path(parser_file) if parser_file else None

        # 読み込んだデータを保持
        self.qp: FrequencyWeightedParser | None = None

        self.mvs: list | None = None
        self.time_ids: list | None = None

        self.sql: Dict[str, str] | None = None

        # これはかえる必要あり
        self.mv_sql_generator: SimpleMVSQLGenerator | None = None

        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
            if self.qp:
                self.mv_sql_generator = SimpleMVSQLGenerator(self.qp)

    def load_pickle(self) -> None:

        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f, encoding='bytes')
        except Exception as e:
            print(f"pickle ファイルの読み込みに失敗しました: {e}")
            self.qp = None


    # 全ての子孫ノードを取得する(stackを使った深さ優先探索)
    def get_all_child_nodes(self, node_id: str) -> list[str]:

        if not self.qp or not hasattr(self.qp, 'qm'):
            return []
        
        all_children = []
        stack = [node_id]

        while stack:
            current = stack.pop()
            if current in self.qp.qm.non_leaf_nodes_info:
                children = self.qp.qm.non_leaf_nodes_info[current].children
                all_children.extend(children)
                stack.extend(children)
        # setで重複を排除してソート済みリストで返す
        return sorted(set(all_children))
    
    def _filter_outermost_nodes(self, candidate_nodes: list[str]) -> list[str]:
        """包含関係にあるノードの中で、最も外側（親）のノードのみを返す"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            return candidate_nodes
        
        # 各候補ノードの子孫ノードを取得
        descendants_map = {}
        for node in candidate_nodes:
            descendants_map[node] = set(self.get_all_child_nodes(node))
        
        # 他のノードに含まれていないノード（最も外側）のみを抽出
        outermost_nodes = []
        
        for node in candidate_nodes:
            is_contained = False
            
            # このノードが他のノードの子孫に含まれているかチェック
            for other_node in candidate_nodes:
                if node != other_node and node in descendants_map[other_node]:
                    is_contained = True
                    break
            
            # 他のノードに含まれていない場合のみ追加
            if not is_contained:
                outermost_nodes.append(node)
        
        return sorted(outermost_nodes)
    
    # 作成したいノードのべき集合を取得
    def enumerate_all_combinations(self, target_mv: str):
        
        #　作成したいMVとその子孫ノード
        dependent_nodes = [target_mv]
        dependent_nodes.extend(self.get_all_child_nodes(target_mv))

        # べき集合を生成
        all_mv_comb = []
        for r in range(len(dependent_nodes) + 1):
            for subset in combinations(dependent_nodes, r):
                all_mv_comb.append(sorted(subset))

        return all_mv_comb
    
    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str]) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成（generate_mv_sqlを使用）"""
        if self.mv_sql_generator is None:
            print(f"  エラー: MVSQLGeneratorが初期化されていません")
            return None

        return self.mv_sql_generator.generate_mv_sql(
            node_id,
            existing_mvs,
        )
    
    # leaf_nodeのマイグレーションプラン
    def enumerate_leaf_migration_plans(
            self,
            target_mv: str
    ):
        mv_sqls = {}
        mv_sqls[str([target_mv])] = target_mv # マイグレーションなし
        mv_sql = self.generate_mv_sql_with_existing(target_mv, [])
        if mv_sql:
            mv_sqls["[]"] = mv_sql

        return mv_sqls

    # non_leaf_nodeのマイグレーションプラン
    def enumerate_non_leaf_migration_plans(
            self,
            target_mv: str # non_leaf_nodeを想定
    ):
        # べき集合を取得
        all_mv_comb = self.enumerate_all_combinations(target_mv)

        mv_sqls = {}
        seen = set()
        filtered_children = []

        # 包含関係を考慮し、重複も排除したMVの組み合わせを取得
        for mv_set in all_mv_comb:
            filtered = self._filter_outermost_nodes(mv_set)
            filtered_tuple = tuple(filtered)
            if filtered_tuple not in seen:
                seen.add(filtered_tuple)
                filtered_children.append(filtered)

        # ここでtarget_mvとべき集合の一つを渡してMV作成SQLを取得
        for mv_candidate in filtered_children:
            if target_mv in mv_candidate:
                print(f"マイグレーションなし")
                mv_sqls[str(mv_candidate)] = target_mv
                continue   
            # 新しい MV の SQL を生成、MV候補をキーにして保存
            mv_sql = self.generate_mv_sql_with_existing(target_mv, mv_candidate)
            if mv_sql:
                mv_sqls[str(mv_candidate)] = mv_sql

        return mv_sqls
    

    def save_migration_plans(
            self,
            filename: str = "migration_plans.json"
    ):
        if not self.sql:
            print("エラー: マイグレーションプランが生成されていません")
            return
        # 出力dirのパス
        output_dir = Path(__file__).parent / "time_dependent_output" / "migration_plan"
        output_dir.mkdir(parents=True, exist_ok=True)
        # ファイルパス
        output_file = output_dir / filename

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.sql, f, indent=2, ensure_ascii=False)
            print(f"マイグレーションプランを保存しました: {output_file}")
        except Exception as e:
            print(f"JSONファイルの保存に失敗しました: {e}")

    
    # 全てのノードのマイグレーションプランを取得
    def get_migration_sqls(self):
        """全てのノードに対してマイグレーションプランを取得"""
        if not self.qp or not hasattr(self.qp, 'qm'):
            print("  エラー: FrequencyWeightedParserが初期化されていません")
            return
        
        self.sql = {}

        # 全てのノード（leaf + non_leaf）を取得
        all_nodes = list(self.qp.qm.leaf_nodes_map_r.keys()) + list(self.qp.qm.non_leaf_nodes_info.keys())

        # 各ノードのマイグレーションプランを取得
        for node in all_nodes:
            # leaf_nodeの場合
            if node.startswith("leaf_"):
                self.sql[node] = self.enumerate_leaf_migration_plans(node)

            # non_leaf_nodeの場合
            elif node.startswith("non_leaf_"):
                self.sql[node] = self.enumerate_non_leaf_migration_plans(node)
        
        # JSONファイルとして保存
        self.save_migration_plans()

if __name__ == "__main__":
    #from config.settings import Settings

    # settings = Settings()
    parser_file = Path(__file__).parent / "time_dependent_output" / "qp_class.pkl"

    migrator = GetMigrationPlans(
        parser_file = str(parser_file)
    )

    migrator.get_migration_sqls()






        

            

        



