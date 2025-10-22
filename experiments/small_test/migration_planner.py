import json
import pickle
from pathlib import Path
from typing import Dict, Any
import sys

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# from src.core.query_parser import QueryParser
from experiments.small_test.frequency_weighted_parser import FrequencyWeightedParser
from config.settings import Settings

from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
from experiments.small_test.small_test_schema_provider import SmallTestSchemaProvider


class Migration_Plan:

    def __init__(
            self,
            settings: Settings | None = None,
            parser_file: str | None = None,
            summary_file: str | None = None
    ): 
        self.settings = settings
        self.parser_file = Path(parser_file) if parser_file else None
        self.summary_file = Path(summary_file) if summary_file else None

        #読み込んだデータを保持する属性
        self.qp: FrequencyWeightedParser | None = None
        self.qp_dict: Dict[str, FrequencyWeightedParser] = {}  # 各時刻のQueryParserを保存
        self.summary: Dict[str, Any] | None = None
        # 各時刻のMVを保存
        self.mvs: list | None = None
        self.time_ids: list | None = None
        
        # 本来各タイムステップごとのpickleファイルがあるが、ここで使う子ノードの情報は共通なため1つだけ読み込む
        if self.parser_file and self.parser_file.exists():
            self.load_pickle()
        if self.summary_file and self.summary_file.exists():
            self.load_summary()
            # summaryから各時刻のQueryParserを読み込む
            if self.summary:
                self.load_all_parsers()

    def load_pickle(self) -> None:

        try:
            with open(self.parser_file, 'rb') as f:
                self.qp = pickle.load(f)
            print(f"pickle ファイルを読み込みました: {self.parser_file}")
        except Exception as e:
            print(f"pickle ファイルの読み込みに失敗しました: {e}")
            self.qp = None

    def load_summary(self) -> None:
        try:
            with open(self.summary_file, 'r', encoding='utf-8') as f:
                self.summary = json.load(f)
            print(f"JSONファイルを読み込みました: {self.summary_file}")
        except Exception as e:
            print(f"JSONファイルの読み込みに失敗しました: {e}")
            self.summary = None
    
    def load_all_parsers(self) -> None:
        """summaryから全ての時刻のQueryParserを読み込む"""
        if not self.summary:
            return
        
        time_ids = self.get_time_id(self.summary)
        output_dir = Path("experiments/small_test/time_dependent_output")
        
        for time_id in time_ids:
            parser_file = output_dir / f"qp_{time_id}.pkl"
            if parser_file.exists():
                try:
                    with open(parser_file, 'rb') as f:
                        qp = pickle.load(f)
                    self.qp_dict[time_id] = qp
                    print(f"  {time_id} のQueryParserを読み込みました: {parser_file}")
                except Exception as e:
                    print(f"  {time_id} のQueryParserの読み込みに失敗: {e}")
            else:
                print(f"  警告: {parser_file} が見つかりません")
    
    # ファイルから時刻を取得
    def get_time_id(self, data: list):
        time_ids =[]
        for item in data:
            time_ids.append(item.get("time_id"))
        return time_ids
    
    # 特定の時刻のMVを取得
    def get_selected_mvs(self, data: list, time_id: str):
        selected_mvs = []
        for item in data:
            if item.get("time_id") == time_id:
                selected_mvs = item.get("selected_mvs", [])
        return selected_mvs
    
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
        # setで重複を排除して返す
        return list(set(all_children))

    def generate_mv_sql_with_existing(self, node_id: str, existing_mvs: list[str], time_id: str) -> str | None:
        """既存のMVを利用して新しいMVのSQLを作成"""
        # 指定された時刻のQueryParserを使用
        if time_id not in self.qp_dict:
            print(f"  エラー: {time_id} のQueryParserが見つかりません")
            return None
        
        target_qp = self.qp_dict[time_id]
        if not hasattr(target_qp, 'qm'):
            return None
        
        try:
            # schema_providerを初期化
            schema_provider = SmallTestSchemaProvider()

            # EnhancedMVGeneratorを初期化
            mv_generator = EnhancedMVGenerator(
                query_manager = target_qp.qm,
                schema_provider = schema_provider,
                selected_mvs = set(existing_mvs) #ここで既存MVを指定
            )

            create_sql = mv_generator.generate_mv_sql(node_id)
            
            if not create_sql:
                print(f"SQL生成失敗: {node_id}")
                return None
            
            print(f"  [INFO] {node_id} のSQL生成完了")
            print(f"  [INFO] 再利用するMV: {existing_mvs if existing_mvs else 'なし'}")
            
            # 既存MVをFROM句で参照するように置き換え
            # EnhancedMVGeneratorが子ノードをMVとして参照していない場合の対処
            if existing_mvs:
                
                # 各子ノードのテーブル名をMV名に置き換え
                for child_node_id in existing_mvs:
                    
                    # 全てのQueryParserから子ノードの情報を検索　これにより書き換えが正しく行われた
                    found = False
                    for qp_time_id, qp in self.qp_dict.items():
                        # leaf_nodeの場合
                        if child_node_id in qp.qm.leaf_nodes_map_r:
                            operator, table_name, alias, filter_cond = qp.qm.leaf_nodes_map_r[child_node_id]
                            mv_name = child_node_id  # mv_プレフィックスなし
                            found = True
                            
                            print(f"    [DEBUG] {qp_time_id} でleaf発見: table_name={table_name}, alias={alias}")
                            
                            # FROM句でテーブル名をMV名に置き換え
                            # 例: "FROM orders AS o" -> "FROM leaf_1 AS o"
                            import re
                            # パターン1: FROM table_name AS alias
                            pattern1 = rf'\bFROM\s+{table_name}\s+AS\s+{alias}\b'
                            before_sql = create_sql
                            create_sql = re.sub(pattern1, rf'FROM {mv_name} AS {alias}', create_sql)
                            if before_sql != create_sql:
                                print(f"    [DEBUG] パターン1でマッチ: '{pattern1}'")
                            
                            # パターン2: , table_name AS alias (JOIN内)
                            pattern2 = rf',\s+{table_name}\s+AS\s+{alias}\b'
                            before_sql = create_sql
                            create_sql = re.sub(pattern2, rf', {mv_name} AS {alias}', create_sql)
                            if before_sql != create_sql:
                                print(f"    [DEBUG] パターン2でマッチ: '{pattern2}'")
                            
                            print(f"  → {child_node_id} ({table_name}) を {mv_name} に置き換え")
                            break
                        
                        
                        # non_leaf_nodeの場合　この場合はまだ試せていない　
                        # 本来は別のモジュールで作りたい　MVgeneratorに組み込む等
                        
                        elif child_node_id in qp.qm.non_leaf_nodes_info:
                            non_leaf_info = qp.qm.non_leaf_nodes_info[child_node_id]
                            mv_name = child_node_id  # mv_プレフィックスなし
                            found = True
                            
                            print(f"    [DEBUG] {qp_time_id} でnon_leaf発見: {child_node_id}, children={non_leaf_info.children}")
                            
                            # non_leaf_nodeの全ての子ノードを取得
                            child_nodes = non_leaf_info.children
                            
                            # 子ノードに含まれる全てのテーブルを特定
                            # 再帰的に子ノードのテーブルを収集
                            def get_all_tables(node_id: str, qp) -> list[tuple[str, str]]:
                                """ノードIDから全てのテーブル(table_name, alias)を再帰的に取得"""
                                tables = []
                                if node_id in qp.qm.leaf_nodes_map_r:
                                    operator, table_name, alias, filter_cond = qp.qm.leaf_nodes_map_r[node_id]
                                    tables.append((table_name, alias))
                                elif node_id in qp.qm.non_leaf_nodes_info:
                                    info = qp.qm.non_leaf_nodes_info[node_id]
                                    for child in info.children:
                                        tables.extend(get_all_tables(child, qp))
                                return tables
                            
                            all_tables = get_all_tables(child_node_id, qp)
                            print(f"    [DEBUG] non_leaf_nodeに含まれるテーブル: {all_tables}")
                            
                            # これらのテーブルが結合されている部分を、MVへの参照に置き換える
                            # 複雑な置き換えが必要なため、ここでは簡易的な実装
                            # TODO: より高度な置き換えロジックを実装
                            
                            # 最初のテーブルをMVに置き換え、残りのテーブルを削除する戦略
                            if all_tables:
                                first_table, first_alias = all_tables[0]
                                import re
                                
                                # 最初のテーブルをMVに置き換え
                                pattern1 = rf'\bFROM\s+{first_table}\s+AS\s+{first_alias}\b'
                                create_sql = re.sub(pattern1, rf'FROM {mv_name} AS {first_alias}', create_sql)
                                
                                # 残りのテーブルとそのJOIN条件を削除
                                for table_name, alias in all_tables[1:]:
                                    # ", table AS alias" パターンを削除
                                    pattern = rf',\s+{table_name}\s+AS\s+{alias}\b'
                                    create_sql = re.sub(pattern, '', create_sql)
                                
                                print(f"  → {child_node_id} を {mv_name} に置き換え (含まれるテーブル: {len(all_tables)}個)")
                            
                            break
                    
                    if not found:
                        print(f"    [DEBUG] {child_node_id} は全てのQueryParserで見つかりませんでした")
            
            print(f"  [DEBUG] 最終SQL (最初の200文字): {create_sql[:200]}")
            return create_sql

        except Exception as e:
            print(f"SQL生成失敗: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _generate_sql_file(self, timestep_key: str, drop_sqls: dict, create_sqls: dict):
        """マイグレーションSQLファイルを生成"""
        sql_file = Path(f"experiments/small_test/time_dependent_output/{timestep_key.replace(' -> ', '_to_')}.sql")
        
        with open(sql_file, 'w', encoding='utf-8') as f:
            f.write(f"-- {timestep_key} のマイグレーション SQL\n")
            f.write("-- =====================================================\n\n")
        
            # CREATE SQL
            if create_sqls:
                f.write("-- CREATE MATERIALIZED VIEW\n")
                for create_sql in create_sqls.values():
                    f.write(f"{create_sql}\n\n")

             # DROP SQL
            if drop_sqls:
                f.write("-- DROP MATERIALIZED VIEW\n")
                for drop_sql in drop_sqls.values():
                    f.write(f"{drop_sql}\n")
                f.write("\n")
            
        
        print(f"SQLファイルを生成しました: {sql_file}")


    def get_migration_plan(self):

        migration_data = {} # マイグレーションプランを保存

        # 各時刻のMVを格納
        for time_id in self.get_time_id(self.summary):
            if self.time_ids is None:
                self.time_ids = []
            if self.mvs is None:
                self.mvs = []
            self.time_ids.append(time_id)
            self.mvs.append(self.get_selected_mvs(self.summary, time_id))
        
        #前の時刻と同じMVがあるか探す
        for i in range(len(self.time_ids)-1):
            before_mvs = set(self.mvs[i])
            after_mvs = set(self.mvs[i+1])
            common_mvs = list(before_mvs.intersection(after_mvs))
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] 共通MV: {common_mvs}")

            # 共通なMVをなくす
            unique_after_mvs = [mv for mv in after_mvs if mv not in common_mvs]

            # leaf_node だけ取り出す
            if unique_after_mvs is None:
                return           
            leaf_nodes = [mv for mv in unique_after_mvs if mv.startswith("leaf_")]
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] ユニークなleaf_node: {leaf_nodes}")

            # leaf_nodeの生成SQLを作成、辞書に保存
            mv_sqls = {}

            for leaf in leaf_nodes:
                mv_sql = self.generate_mv_sql_with_existing(leaf, list(before_mvs), self.time_ids[i+1])
                if mv_sql:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {leaf} の生成SQL: {mv_sql}")
                    mv_sqls[leaf] = mv_sql
                else:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {leaf} のSQL生成失敗")

            # non_leaf_nodeを取り出す
            non_leaf_nodes = [mv for mv in unique_after_mvs if mv.startswith("non_leaf_")]

            # 利用できるMVのあるnon_leaf_nodeを格納
            non_leaf_nodes_with_mv = {}
            # 各non_leaf_nodeの全ての子ノードを格納
            all_children_dict = {}
            for node in non_leaf_nodes:
                all_children_dict[node] = self.get_all_child_nodes(node)
                print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}の全ての子ノード: {all_children_dict[node]}")
                # 各non_leaf_nodeについて、その子ノードの中にbefore_mvsに含まれているものがあるかを確認
                common_children = list(before_mvs.intersection(set(all_children_dict[node])))
                if common_children:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}は{common_children}を利用する")
                    non_leaf_nodes_with_mv[node] = common_children
                    # 新しい MV の SQL を生成　このパターン未確認
                    mv_sql_non = self.generate_mv_sql_with_existing(node, common_children, self.time_ids[i+1])
                    if mv_sql_non:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の生成SQL作成")
                        mv_sqls[node] = mv_sql_non # SQLを保存
                    else:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")
                else:
                    print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node}は新規に配置が必要")
                    # 新規の場合も SQL 生成可能（existing_mvs を空で）
                    mv_sql_non_new = self.generate_mv_sql_with_existing(node, [], self.time_ids[i+1])
                    if mv_sql_non_new:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} の新規生成SQL作成")
                        mv_sqls[node] = mv_sql_non_new # SQLを保存
                    else:
                        print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] {node} のSQL生成失敗")

            # DROP SQL を生成（before_mvs の中で after_mvs に含まれないもの）　これは実行のタイミングが分からない
            mvs_to_drop = [mv for mv in before_mvs if mv not in after_mvs]
            drop_sqls = {}
            for mv in mvs_to_drop:
                drop_sqls[mv] = f"DROP MATERIALIZED VIEW IF EXISTS {mv};"  # mv_プレフィックスなし
            
            print(f"[{self.time_ids[i]} -> {self.time_ids[i+1]}] DROP対象のMV: {mvs_to_drop}")
            
            # 辞書形式で保存
            migration_data[f"{self.time_ids[i]} -> {self.time_ids[i+1]}"] = {
                "common_mvs": common_mvs,
                "generate_leaf_nodes": leaf_nodes,
                "generate_non_leaf_nodes_0": non_leaf_nodes,
                "generate_non_leaf_nodes_with_mv": non_leaf_nodes_with_mv,
                "migration_plans_sql": mv_sqls,
                "drop_mvs": mvs_to_drop,
                "drop_sqls": drop_sqls
            }
        # JSONファイルに保存
        output_file = Path("experiments/small_test/time_dependent_output/migration_plan.json")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(migration_data, f, indent=2, ensure_ascii=False)
        print(f"マイグレーションプランを{output_file}に保存しました")

            # SQL ファイルを生成
        self._generate_sql_file(f"{self.time_ids[i]} -> {self.time_ids[i+1]}", drop_sqls, mv_sqls)

"""
todo :
他のパターンも試す->もっとクエリ増やしてもいいかも
jsonで書き出す=>完了
コストの計算もいれたい->EXPLAIN
SQL生成クエリの書き換えと同じ方法でしてみる
MVではなくTABLEにするうかも？ このままでは1パターン
"""

            


                

if __name__ == "__main__":

    # ファイルパスの設定（必要に応じて変更）
    parser_file = "experiments/small_test/time_dependent_output/qp_morning.pkl"  # pickle ファイル（子ノード情報用）
    summary_file = "experiments/small_test/time_dependent_output/normal_summary.json"  # JSON ファイル
    
    # Migration_Plan のインスタンス作成
    plan = Migration_Plan(parser_file=parser_file, summary_file=summary_file)

    if plan.summary:
        plan.get_migration_plan()
    else:
        print("サマリーファイルの読み込み失敗")