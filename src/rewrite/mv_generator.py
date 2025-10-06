"""マテリアライズドビュー生成SQL作成"""
import os
from typing import List, Set, Tuple, Dict, Any
from pathlib import Path

from src.rewrite.sql_parser import SQLParser
from src.rewrite.schema import get_table_columns, validate_table


class MVGenerator:
    """マテリアライズドビュー生成SQLの作成"""
    
    def __init__(self):
        """初期化"""
        self.sql_parser = SQLParser()
    
    def generate_mv_scripts(
        self,
        mv_nodes: List[str],
        query_manager: Any,
        output_dir: str
    ) -> List[str]:
        """MV作成スクリプトを生成
        
        Args:
            mv_nodes: MVノードIDのリスト
            query_manager: QueryManagerインスタンス
            output_dir: 出力ディレクトリ
            
        Returns:
            生成されたファイルパスのリスト
        """
        os.makedirs(output_dir, exist_ok=True)
        generated_files = []
        
        for node_id in mv_nodes:
            if node_id == "NONE":
                continue
            
            sql = self._generate_mv_sql(node_id, query_manager)
            if sql:
                filepath = os.path.join(output_dir, f"{node_id}.sql")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(sql)
                generated_files.append(filepath)
        
        return generated_files
    
    def _generate_mv_sql(self, node_id: str, qm: Any) -> str:
        """MV作成SQLを生成
        
        Args:
            node_id: ノードID
            qm: QueryManager
            
        Returns:
            CREATE MATERIALIZED VIEW 文
        """
        if node_id.startswith("leaf_"):
            return self._generate_leaf_mv(node_id, qm)
        elif node_id.startswith("non_leaf_"):
            return self._generate_non_leaf_mv(node_id, qm)
        else:
            return ""
    
    def _generate_leaf_mv(self, leaf_id: str, qm: Any) -> str:
        """リーフノード用MV生成SQL
        
        Args:
            leaf_id: リーフノードID
            qm: QueryManager
            
        Returns:
            CREATE文
        """
        if not hasattr(qm, 'leaf_nodes_map') or leaf_id not in qm.leaf_nodes_map:
            return ""
        
        leaf_node = qm.leaf_nodes_map[leaf_id]
        table_name = leaf_node.get('table_name', '')
        alias = leaf_node.get('alias', table_name)
        conditions = leaf_node.get('conditions', '')
        
        if not table_name:
            return ""
        
        try:
            columns = get_table_columns(table_name)
        except KeyError:
            print(f"Warning: Unknown table {table_name}, using *")
            columns = ["*"]
        
        # SELECT句作成
        if columns == ["*"]:
            select_clause = "*"
        else:
            select_clause = ", ".join([f"{alias}.{col}" for col in columns])
        
        # WHERE句
        where_clause = conditions if conditions else ""
        
        # SQL組み立て
        sql = f"CREATE MATERIALIZED VIEW {leaf_id} AS\n"
        sql += self.sql_parser.reconstruct_query(
            select_clause=select_clause,
            from_clause=f"{table_name} {alias}",
            where_clause=where_clause
        )
        sql += ";\n"
        
        return sql
    
    def _generate_non_leaf_mv(self, non_leaf_id: str, qm: Any) -> str:
        """非リーフノード用MV生成SQL
        
        Args:
            non_leaf_id: 非リーフノードID
            qm: QueryManager
            
        Returns:
            CREATE文
        """
        if not hasattr(qm, 'non_leaf_nodes_map') or non_leaf_id not in qm.non_leaf_nodes_map:
            return ""
        
        non_leaf_node = qm.non_leaf_nodes_map[non_leaf_id]
        
        # 子ノード取得
        if hasattr(qm, 'non_leaf_nodes_map_r') and non_leaf_id in qm.non_leaf_nodes_map_r:
            child_ids = qm.non_leaf_nodes_map_r[non_leaf_id]
        else:
            child_ids = []
        
        if not child_ids or len(child_ids) < 2:
            # 子ノードが不足している場合は簡易版
            sql = f"CREATE MATERIALIZED VIEW {non_leaf_id} AS\n"
            sql += "-- Non-leaf node (children not fully resolved)\n"
            sql += "SELECT * FROM placeholder;\n"
            return sql
        
        # FROM句の構築（子ノードを使用）
        from_parts = []
        for child_id in child_ids:
            from_parts.append(child_id)
        
        from_clause = from_parts[0]
        for i, child in enumerate(from_parts[1:], 1):
            # 簡易的なJOIN（実際のJOIN条件は別途必要）
            from_clause += f"\nJOIN {child} ON {from_parts[0]}.id = {child}.id"
        
        # SELECT句（全カラム）
        select_clause = "*"
        
        sql = f"CREATE MATERIALIZED VIEW {non_leaf_id} AS\n"
        sql += self.sql_parser.reconstruct_query(
            select_clause=select_clause,
            from_clause=from_clause
        )
        sql += ";\n"
        
        return sql
    
    def save_create_sqls(
        self,
        mv_data: List[Dict[str, Any]],
        output_dir: Path
    ) -> None:
        """MV作成SQLをファイルに保存
        
        Args:
            mv_data: MV情報のリスト
            output_dir: 出力ディレクトリ
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        
        for mv in mv_data:
            view_id = mv.get('view_id', '')
            create_sql = mv.get('create_sql', '')
            
            if view_id and create_sql:
                sql_file = output_dir / f"{view_id}.sql"
                with open(sql_file, 'w', encoding='utf-8') as f:
                    f.write(create_sql)
                
                print(f"Saved MV creation SQL: {sql_file}")
