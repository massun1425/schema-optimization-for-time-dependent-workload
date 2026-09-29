"""Generation of SQL for creating materialized views"""

import os
from pathlib import Path
from typing import Any

from src.rewrite.schema import get_table_columns
from src.rewrite.sql_parser import SQLParser


class MVGenerator:
    """Builds SQL for creating materialized views"""

    def __init__(self):
        """Initialize"""
        self.sql_parser = SQLParser()

    def generate_mv_scripts(
        self, mv_nodes: list[str], query_manager: Any, output_dir: str
    ) -> list[str]:
        """Generate MV creation scripts

        Args:
            mv_nodes: List of MV node IDs
            query_manager: QueryManager instance
            output_dir: Output directory

        Returns:
            List of generated file paths
        """
        # Clean up existing SQL files
        output_path = Path(output_dir)
        for file_path in output_path.glob("*.sql"):
            file_path.unlink()
        
        os.makedirs(output_dir, exist_ok=True)
        generated_files = []

        for node_id in mv_nodes:
            if node_id == "NONE":
                continue

            sql = self._generate_mv_sql(node_id, query_manager)
            if sql:
                filepath = os.path.join(output_dir, f"{node_id}.sql")
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(sql)
                generated_files.append(filepath)

        return generated_files

    def _generate_mv_sql(self, node_id: str, qm: Any) -> str:
        """Generate the MV creation SQL

        Args:
            node_id: Node ID
            qm: QueryManager

        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id.startswith("leaf_"):
            return self._generate_leaf_mv(node_id, qm)
        elif node_id.startswith("non_leaf_"):
            return self._generate_non_leaf_mv(node_id, qm)
        else:
            return ""

    def _generate_leaf_mv(self, leaf_id: str, qm: Any) -> str:
        """MV creation SQL for a leaf node

        Args:
            leaf_id: Leaf node ID
            qm: QueryManager

        Returns:
            CREATE statement
        """
        if not hasattr(qm, "leaf_nodes_map_r") or leaf_id not in qm.leaf_nodes_map_r:
            print(f"Warning: {leaf_id} not found in leaf_nodes_map_r")
            return ""

        # Get the information from leaf_nodes_map_r: (operator, table_name, alias, conditions)
        operator, table_name, alias, conditions = qm.leaf_nodes_map_r[leaf_id]

        if not table_name:
            return ""

        try:
            columns = get_table_columns(table_name)
        except KeyError:
            print(f"Warning: Unknown table {table_name}, using *")
            columns = ["*"]

        # Build the SELECT clause
        if columns == ["*"]:
            select_clause = "*"
        else:
            select_clause = ", ".join([f"{alias}.{col}" for col in columns])

        # WHERE clause
        where_clause = conditions if conditions else ""

        # Assemble the SQL
        sql = f"CREATE MATERIALIZED VIEW {leaf_id} AS\n"
        sql += self.sql_parser.reconstruct_query(
            select_clause=select_clause,
            from_clause=f"{table_name} {alias}",
            where_clause=where_clause,
        )
        sql += ";\n"

        return sql

    def _generate_non_leaf_mv(self, non_leaf_id: str, qm: Any) -> str:
        """MV creation SQL for a non-leaf node

        Args:
            non_leaf_id: Non-leaf node ID
            qm: QueryManager

        Returns:
            CREATE statement
        """
        if not hasattr(qm, "non_leaf_nodes_map") or non_leaf_id not in qm.non_leaf_nodes_map:
            return ""

        # Get the child nodes
        if hasattr(qm, "non_leaf_nodes_map_r") and non_leaf_id in qm.non_leaf_nodes_map_r:
            child_ids = qm.non_leaf_nodes_map_r[non_leaf_id]
        else:
            child_ids = []

        if not child_ids or len(child_ids) < 2:
            # Simplified version when there are not enough child nodes
            sql = f"CREATE MATERIALIZED VIEW {non_leaf_id} AS\n"
            sql += "-- Non-leaf node (children not fully resolved)\n"
            sql += "SELECT * FROM placeholder;\n"
            return sql

        # Build the FROM clause (using the child nodes)
        from_parts = []
        for child_id in child_ids:
            from_parts.append(child_id)

        from_clause = from_parts[0]
        for i, child in enumerate(from_parts[1:], 1):
            # Simplified JOIN (the actual JOIN conditions must be provided separately)
            from_clause += f"\nJOIN {child} ON {from_parts[0]}.id = {child}.id"

        # SELECT clause (all columns)
        select_clause = "*"

        sql = f"CREATE MATERIALIZED VIEW {non_leaf_id} AS\n"
        sql += self.sql_parser.reconstruct_query(
            select_clause=select_clause, from_clause=from_clause
        )
        sql += ";\n"

        return sql

    def save_create_sqls(self, mv_data: list[dict[str, Any]], output_dir: Path) -> None:
        """Save the MV creation SQL to files

        Args:
            mv_data: List of MV information
            output_dir: Output directory
        """
        # Clean up existing SQL files
        for file_path in output_dir.glob("*.sql"):
            file_path.unlink()
        
        output_dir.mkdir(parents=True, exist_ok=True)

        for mv in mv_data:
            view_id = mv.get("view_id", "")
            create_sql = mv.get("create_sql", "")

            if view_id and create_sql:
                sql_file = output_dir / f"{view_id}.sql"
                with open(sql_file, "w", encoding="utf-8") as f:
                    f.write(create_sql)

                print(f"Saved MV creation SQL: {sql_file}")
