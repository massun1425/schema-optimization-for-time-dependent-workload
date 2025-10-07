"""Enhanced MV Generator with accurate JOIN condition handling.

This module provides EnhancedMVGenerator class that generates accurate
materialized view creation SQL using the enhanced JOIN information from
QueryParser and QueryManager.
"""

import logging
from typing import Any, Optional

from src.core.models import NonLeafNodeInfo, JoinCondition
from src.rewrite.schema_provider import SchemaProvider

logger = logging.getLogger(__name__)


class EnhancedMVGenerator:
    """Enhanced materialized view SQL generator (Chapter 4).
    
    This class generates accurate MV creation SQL by utilizing:
    - Complete JOIN condition information from NonLeafNodeInfo
    - Dynamic schema information from SchemaProvider
    - Proper child node ordering preservation
    
    Attributes:
        schema_provider: SchemaProvider for dynamic schema info
        qm: QueryManager instance
    """

    def __init__(self, query_manager: Any, schema_provider: Optional[SchemaProvider] = None):
        """Initialize EnhancedMVGenerator.
        
        Args:
            query_manager: QueryManager instance with enhanced node info
            schema_provider: Optional SchemaProvider for dynamic schema.
                           If None, will use fallback static schema.
        """
        self.qm = query_manager
        self.schema_provider = schema_provider
        
    def generate_mv_sql(self, node_id: str) -> str:
        """Generate MV creation SQL for a node.
        
        Args:
            node_id: Node ID (leaf_X or non_leaf_X)
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id.startswith("leaf_"):
            return self.generate_leaf_mv_sql(node_id)
        elif node_id.startswith("non_leaf_"):
            return self.generate_non_leaf_mv_sql(node_id)
        else:
            logger.warning(f"Unknown node type: {node_id}")
            return ""

    def generate_leaf_mv_sql(self, node_id: str) -> str:
        """Generate leaf MV creation SQL (Chapter 4).
        
        Args:
            node_id: Leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id not in self.qm.leaf_nodes_map_r:
            logger.error(f"Leaf node {node_id} not found")
            return ""
        
        operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
        
        if not table:
            logger.error(f"No table name for {node_id}")
            return ""
        
        # Get columns dynamically from schema
        columns = self._get_table_columns(table)
        
        # Build SELECT clause
        if columns:
            select_items = [f"{alias}.{col}" for col in columns]
            select_clause = ", ".join(select_items)
        else:
            select_clause = f"{alias}.*"
            logger.warning(f"No columns found for {table}, using *")
        
        # Build SQL
        sql_parts = [
            f"CREATE MATERIALIZED VIEW {node_id} AS",
            f"SELECT {select_clause}",
            f"FROM {table} AS {alias}"
        ]
        
        if filter_condition:
            sql_parts.append(f"WHERE {filter_condition}")
        
        sql_parts.append(";")
        
        return "\n".join(sql_parts)

    def generate_non_leaf_mv_sql(self, node_id: str) -> str:
        """Generate non-leaf MV creation SQL with accurate JOIN conditions (Chapter 4).
        
        This is the core improvement: we use the stored JOIN condition information
        to generate accurate JOIN clauses instead of guessing.
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        # Check if enhanced info is available
        if node_id in self.qm.non_leaf_nodes_info:
            return self._generate_non_leaf_mv_enhanced(node_id)
        else:
            # Fallback to legacy method
            logger.warning(f"No enhanced info for {node_id}, using fallback")
            return self._generate_non_leaf_mv_fallback(node_id)

    def _generate_non_leaf_mv_enhanced(self, node_id: str) -> str:
        """Generate non-leaf MV using enhanced information.
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        node_info = self.qm.non_leaf_nodes_info[node_id]
        
        if not node_info.children:
            logger.error(f"No children for {node_id}")
            return ""
        
        # Get child information
        child_mvs = []
        for child_id in node_info.children:
            child_mvs.append({
                'id': child_id,
                'tables': self._get_child_tables(child_id)
            })
        
        # Build FROM clause: start with first child
        from_parts = [child_mvs[0]['id']]
        
        # Build JOIN clauses for remaining children
        for i, child_mv in enumerate(child_mvs[1:], 1):
            join_clause = self._build_join_clause(
                left_mv=child_mvs[0]['id'],
                right_mv=child_mv['id'],
                join_type=node_info.join_type,
                join_conditions=node_info.join_conditions,
                left_tables=child_mvs[0]['tables'],
                right_tables=child_mv['tables']
            )
            from_parts.append(join_clause)
        
        from_clause = "\n".join(from_parts)
        
        # Build SELECT clause: select all columns from all children
        select_clause = self._build_select_clause(child_mvs)
        
        # Build WHERE clause from additional filters
        where_clause = ""
        if node_info.filters:
            # Rewrite filters to use MV names instead of original table aliases
            rewritten_filters = []
            for filter_str in node_info.filters:
                rewritten = self._rewrite_filter_for_mvs(filter_str, child_mvs)
                if rewritten:
                    rewritten_filters.append(rewritten)
            
            if rewritten_filters:
                where_clause = f"\nWHERE {' AND '.join(rewritten_filters)}"
        
        # Build final SQL
        sql = f"""CREATE MATERIALIZED VIEW {node_id} AS
SELECT {select_clause}
FROM {from_clause}{where_clause};"""
        
        return sql

    def _build_join_clause(
        self,
        left_mv: str,
        right_mv: str,
        join_type: str,
        join_conditions: list[JoinCondition],
        left_tables: list[str],
        right_tables: list[str]
    ) -> str:
        """Build JOIN clause for two child MVs.
        
        Args:
            left_mv: Left MV node ID
            right_mv: Right MV node ID
            join_type: JOIN type (Inner, Left, Right, etc.)
            join_conditions: List of JOIN conditions
            left_tables: Table aliases covered by left MV
            right_tables: Table aliases covered by right MV
            
        Returns:
            JOIN clause string (e.g., "INNER JOIN mv_2 ON mv_1.id = mv_2.ref_id")
        """
        # Find conditions that connect these two MVs
        matching_conditions = self._find_join_conditions_for_mvs(
            join_conditions, left_tables, right_tables
        )
        
        if matching_conditions:
            # Build condition string
            condition_parts = []
            for jc in matching_conditions:
                # Determine which alias is in which MV and rewrite to use MV names
                if jc.left_table in left_tables and jc.right_table in right_tables:
                    condition_parts.append(
                        f"{left_mv}.{jc.left_column} {jc.operator} {right_mv}.{jc.right_column}"
                    )
                elif jc.right_table in left_tables and jc.left_table in right_tables:
                    condition_parts.append(
                        f"{left_mv}.{jc.right_column} {jc.operator} {right_mv}.{jc.left_column}"
                    )
                else:
                    # Condition might reference tables in the same MV
                    logger.warning(f"Join condition references tables not in MVs: {jc}")
            
            if condition_parts:
                condition_str = " AND ".join(condition_parts)
            else:
                condition_str = "TRUE  -- WARNING: Could not map join conditions to MVs"
        else:
            # Try to infer from foreign keys
            condition_str = self._infer_join_condition(
                left_mv, right_mv, left_tables, right_tables
            )
        
        return f"{join_type} JOIN {right_mv} ON {condition_str}"

    def _find_join_conditions_for_mvs(
        self,
        join_conditions: list[JoinCondition],
        left_tables: list[str],
        right_tables: list[str]
    ) -> list[JoinCondition]:
        """Find JOIN conditions that connect two sets of tables.
        
        Args:
            join_conditions: All JOIN conditions
            left_tables: Tables in left MV
            right_tables: Tables in right MV
            
        Returns:
            List of matching JoinCondition objects
        """
        matching = []
        
        for jc in join_conditions:
            # Check if this condition connects the two MVs
            if (jc.left_table in left_tables and jc.right_table in right_tables) or \
               (jc.right_table in left_tables and jc.left_table in right_tables):
                matching.append(jc)
        
        return matching

    def _infer_join_condition(
        self,
        left_mv: str,
        right_mv: str,
        left_tables: list[str],
        right_tables: list[str]
    ) -> str:
        """Infer JOIN condition from foreign key relationships.
        
        Args:
            left_mv: Left MV node ID
            right_mv: Right MV node ID
            left_tables: Tables in left MV
            right_tables: Tables in right MV
            
        Returns:
            JOIN condition string
        """
        if not self.schema_provider:
            logger.warning(f"No schema provider, cannot infer JOIN between {left_mv} and {right_mv}")
            return "TRUE  -- WARNING: Join condition could not be inferred"
        
        try:
            # Try to find FK relationship
            fk_relations = self.schema_provider.get_foreign_key_relations(
                left_tables, right_tables
            )
            
            if fk_relations:
                # Use first FK relationship
                fk = fk_relations[0]
                logger.info(
                    f"Inferred JOIN: {left_mv}.{fk.from_column} = {right_mv}.{fk.to_column}"
                )
                return f"{left_mv}.{fk.from_column} = {right_mv}.{fk.to_column}"
            else:
                logger.warning(f"No FK found between {left_tables} and {right_tables}")
                return "TRUE  -- WARNING: No FK relationship found"
                
        except Exception as e:
            logger.error(f"Error inferring JOIN condition: {e}")
            return "TRUE  -- WARNING: Error inferring join condition"

    def _build_select_clause(self, child_mvs: list[dict]) -> str:
        """Build SELECT clause for non-leaf MV.
        
        Args:
            child_mvs: List of child MV info dicts
            
        Returns:
            SELECT clause string
        """
        # Simple approach: select all from all child MVs
        select_parts = [f"{mv['id']}.*" for mv in child_mvs]
        return ", ".join(select_parts)

    def _rewrite_filter_for_mvs(
        self,
        filter_str: str,
        child_mvs: list[dict]
    ) -> Optional[str]:
        """Rewrite filter condition to use MV names instead of table aliases.
        
        Args:
            filter_str: Original filter string (e.g., "t.year > 2000")
            child_mvs: List of child MV info
            
        Returns:
            Rewritten filter string or None if cannot rewrite
        """
        # This is a simplified implementation
        # In practice, you'd need more sophisticated parsing
        # For now, just return the filter as-is
        # TODO: Implement proper alias rewriting
        logger.debug(f"Filter rewriting not fully implemented: {filter_str}")
        return filter_str

    def _get_child_tables(self, node_id: str) -> list[str]:
        """Get all table aliases covered by a node.
        
        This returns aliases (not table names) because JOIN conditions
        use aliases from the original query.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of table aliases
        """
        aliases = set()
        
        if node_id.startswith("leaf_"):
            # Get alias from leaf node
            if node_id in self.qm.leaf_nodes_map_r:
                operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
                if alias:
                    aliases.add(alias)
        elif node_id.startswith("non_leaf_"):
            # Recursively get aliases from children
            if node_id in self.qm.non_leaf_nodes_map_r:
                for child_id in self.qm.non_leaf_nodes_map_r[node_id]:
                    aliases.update(self._get_child_tables(child_id))
        
        return list(aliases)

    def _get_table_columns(self, table_name: str) -> list[str]:
        """Get columns for a table.
        
        Args:
            table_name: Table name
            
        Returns:
            List of column names
        """
        if self.schema_provider:
            try:
                return self.schema_provider.get_table_columns(table_name)
            except Exception as e:
                logger.warning(f"Error getting columns for {table_name}: {e}")
        
        # Fallback to static schema
        try:
            from .schema import get_table_columns
            return get_table_columns(table_name)
        except KeyError:
            logger.warning(f"Table {table_name} not in schema")
            return []

    def _generate_non_leaf_mv_fallback(self, node_id: str) -> str:
        """Fallback method for generating non-leaf MV without enhanced info.
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        if node_id not in self.qm.non_leaf_nodes_map_r:
            return ""
        
        child_ids = list(self.qm.non_leaf_nodes_map_r[node_id])
        
        if len(child_ids) < 2:
            logger.warning(f"Insufficient children for {node_id}")
            return ""
        
        # Simple fallback: assume simple equality JOIN on 'id'
        from_clause = child_ids[0]
        for child in child_ids[1:]:
            from_clause += f"\nJOIN {child} ON {child_ids[0]}.id = {child}.id"
        
        sql = f"""CREATE MATERIALIZED VIEW {node_id} AS
SELECT *
FROM {from_clause};"""
        
        logger.warning(f"Used fallback generation for {node_id}")
        return sql
