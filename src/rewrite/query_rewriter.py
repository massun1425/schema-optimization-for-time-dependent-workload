"""クエリ書き換えロジック"""
import re
import os
from typing import List, Dict, Any
from pathlib import Path

from src.rewrite.sql_parser import SQLParser
from src.rewrite.mv_generator import MVGenerator


class QueryRewriter:
    """クエリ書き換え管理"""
    
    def __init__(self, query_manager: Any = None):
        """初期化
        
        Args:
            query_manager: クエリ管理オブジェクト
        """
        self.qm = query_manager
        self.sql_parser = SQLParser()
        self.mv_generator = MVGenerator()
    
    def rewrite_workload(
        self,
        mv_selections: Dict[int, List[str]],
        output_dir: str,
        original_queries: Dict[int, str] = None
    ) -> List[str]:
        """ワークロード全体を書き換え
        
        Args:
            mv_selections: {query_id: [MV node IDs]}
            output_dir: 出力ディレクトリ
            original_queries: {query_id: original SQL} (optional)
            
        Returns:
            書き換えられたクエリファイルのパスリスト
        """
        os.makedirs(output_dir, exist_ok=True)
        rewritten_files = []
        
        for query_id, mv_nodes in mv_selections.items():
            if not mv_nodes or mv_nodes[0] == "NONE":
                continue
            
            # 元のクエリ取得
            if original_queries and query_id in original_queries:
                original_sql = original_queries[query_id]
            elif self.qm and hasattr(self.qm, 'query_map') and query_id in self.qm.query_map:
                original_sql = self.qm.query_map[query_id].get('original_sql', '')
            else:
                print(f"Warning: No original SQL for query {query_id}")
                continue
            
            # クエリ書き換え
            rewritten_sql = self._rewrite_query(query_id, mv_nodes, original_sql)
            
            # ファイル保存
            filename = f"query_{query_id}.sql"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(rewritten_sql)
            
            rewritten_files.append(filepath)
            print(f"Rewritten query {query_id}: {filepath}")
        
        return rewritten_files
    
    def _rewrite_query(
        self,
        query_id: int,
        mv_nodes: List[str],
        original_sql: str
    ) -> str:
        """クエリを書き換え
        
        Args:
            query_id: クエリID
            mv_nodes: 使用するMVノードIDリスト
            original_sql: 元のSQL
            
        Returns:
            書き換え後のSQL
        """
        if not mv_nodes or not original_sql:
            return original_sql
        
        # FROM句を解析
        from_clause = self.sql_parser.extract_from_clause(original_sql)
        where_clause = self.sql_parser.extract_where_clause(original_sql)
        
        # テーブルリスト取得
        tables = self.sql_parser.extract_tables(from_clause)
        
        # リーフノードをMVで置換
        new_from_parts = []
        replaced_tables = set()
        
        for table, alias in tables:
            replaced = False
            
            # このテーブルに対応するMVがあるか確認
            if self.qm and hasattr(self.qm, 'leaf_nodes_map'):
                for mv_node in mv_nodes:
                    if mv_node.startswith("leaf_") and mv_node in self.qm.leaf_nodes_map:
                        leaf_info = self.qm.leaf_nodes_map[mv_node]
                        if leaf_info.get('table_name') == table:
                            new_from_parts.append(f"{mv_node} {alias}")
                            replaced_tables.add(table)
                            replaced = True
                            print(f"  Replaced {table} with {mv_node}")
                            break
            
            if not replaced:
                new_from_parts.append(f"{table} {alias}")
        
        # 新しいFROM句
        new_from = ", ".join(new_from_parts)
        
        # SELECT句を元のまま抽出
        select_match = re.search(r'SELECT\s+(.+?)\s+FROM', original_sql, re.IGNORECASE | re.DOTALL)
        select_clause = select_match.group(1) if select_match else "*"
        
        # SQLを再構築
        rewritten_sql = self.sql_parser.reconstruct_query(
            select_clause=select_clause,
            from_clause=new_from,
            where_clause=where_clause
        )
        
        return rewritten_sql
    
    def generate_mv_creation_scripts(
        self,
        mv_nodes: List[str],
        output_dir: Path
    ) -> List[str]:
        """MV作成スクリプトを生成
        
        Args:
            mv_nodes: MVノードIDリスト
            output_dir: 出力ディレクトリ
            
        Returns:
            生成されたファイルパスのリスト
        """
        if not self.qm:
            print("Warning: No QueryManager available")
            return []
        
        return self.mv_generator.generate_mv_scripts(
            mv_nodes,
            self.qm,
            str(output_dir)
        )


def load_mv_selections(mv_list_file: str) -> Dict[int, List[str]]:
    """MV選択結果をCSVから読み込み
    
    Args:
        mv_list_file: mv_y_list.csv のパス
        
    Returns:
        {query_num: [MV node IDs]}
    """
    import csv
    
    mv_selections = {}
    
    if not os.path.exists(mv_list_file):
        return mv_selections
    
    with open(mv_list_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if row:
                mv_selections[i] = [node.strip() for node in row if node.strip()]
            else:
                mv_selections[i] = ["NONE"]
    
    return mv_selections
