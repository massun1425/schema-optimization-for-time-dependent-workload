"""Enhanced MV Generator with accurate JOIN condition handling.

This module provides EnhancedMVGenerator class that generates accurate
materialized view creation SQL using the enhanced JOIN information from
QueryParser and QueryManager.

Modified version: leaf nodes are also selectable as MVs.
"""

import logging
import re
from typing import Any, Optional

from src.core.models import NonLeafNodeInfo, JoinCondition
from src.rewrite.schema_provider import SchemaProvider

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.WARNING)


class EnhancedMVGenerator:
    """Enhanced materialized view SQL generator (Chapter 4).
    
    This class generates accurate MV creation SQL by utilizing:
    - Complete JOIN condition information from NonLeafNodeInfo
    - Dynamic schema information from SchemaProvider
    - Proper child node ordering preservation
    
    Modified: leaf nodes can also be selected as MVs.
    
    Attributes:
        schema_provider: SchemaProvider for dynamic schema info
        qm: QueryManager instance
        selected_mvs: Set of selected MV node IDs (both leaf and non-leaf)
    """

    def __init__(self, query_manager: Any, schema_provider: Optional[SchemaProvider] = None, selected_mvs: Optional[set] = None, query_parser: Any = None):
        """Initialize EnhancedMVGenerator.
        
        Args:
            query_manager: QueryManager instance with enhanced node info
            schema_provider: Optional SchemaProvider for dynamic schema.
                           If None, will use fallback static schema.
            selected_mvs: Optional set of selected MV node IDs (both leaf and non-leaf).
                         If a child node is not in this set, it will be expanded as a subquery.
            query_parser: Optional QueryParser instance for accessing original SQL
                         JOIN conditions (used to supplement execution-plan-derived conditions).
        """
        self.qm = query_manager
        self.schema_provider = schema_provider
        self.selected_mvs = selected_mvs if selected_mvs is not None else set()
        self.query_parser = query_parser
        
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
        
        Flat expansion: child nodes are recursively expanded down to the table level,
        and all joins are listed flat instead of as nested subqueries.
        
        Args:
            node_id: Non-leaf node ID
            
        Returns:
            CREATE MATERIALIZED VIEW statement
        """
        try:
            node_info = self.qm.non_leaf_nodes_info[node_id]
            
            if not node_info.children:
                logger.error(f"No children for {node_id}")
                return ""
            
            # Flatten all child nodes (into tables or selected MVs)
            flat_components = []
            all_join_conditions_set = set()  # use a set for deduplication
            all_filters = list(node_info.filters) if node_info.filters else []
            
            # Flatten each child node
            for child_id in node_info.children:
                child_flat = self._flatten_node(child_id)
                flat_components.append(child_flat)
                # Also collect the join conditions and filters of the child node (deduplicated)
                for jc in child_flat.get('join_conditions', []):
                    all_join_conditions_set.add(jc)
                all_filters.extend(child_flat.get('filters', []))
            
            # Add the join conditions of the current node (deduplicated)
            if node_info.join_conditions:
                for jc in node_info.join_conditions:
                    # Build the join condition only after checking that the table names are non-empty
                    left_table = jc.left_table if jc.left_table else ""
                    right_table = jc.right_table if jc.right_table else ""
                    
                    if left_table and right_table:
                        jc_str = f"{left_table}.{jc.left_column} {jc.operator} {right_table}.{jc.right_column}"
                        all_join_conditions_set.add(jc_str)
                    else:
                        logger.warning(f"JOIN condition has missing table name in node {node_id}: left={left_table}, right={right_table}, columns={jc.left_column}, {jc.right_column}")
            
            # Convert the set to a list
            all_join_conditions = list(all_join_conditions_set)
            
            # Build the FROM clause: the first component
            from_parts = []
            first_comp = flat_components[0]
            
            # The first table/MV
            first_table_added = False
            for table_info in first_comp['tables']:
                if not first_table_added:
                    from_parts.append(f"{table_info['source']} AS {table_info['alias']}")
                    first_table_added = True
                    break
            
            # Build an alias map (for converting table names to aliases)
            table_to_alias = {}  # table_name -> alias
            
            for comp in flat_components:
                for table_info in comp['tables']:
                    source_name = table_info['source']
                    alias = table_info['alias']
                    if not source_name.startswith('mv_'):
                        # Regular table
                        table_to_alias[source_name] = alias
            
            # Collect all join conditions from the whole subtree (added to the existing conditions)
            subtree_join_conditions = self._collect_all_join_conditions(node_info, self.qm)
            for jc in subtree_join_conditions:
                # Build the join condition only after checking that the table names are non-empty
                left_table = jc.left_table if jc.left_table else ""
                right_table = jc.right_table if jc.right_table else ""
                
                if left_table and right_table:
                    jc_str = f"{left_table}.{jc.left_column} {jc.operator} {right_table}.{jc.right_column}"
                    all_join_conditions_set.add(jc_str)
                else:
                    logger.warning(f"JOIN condition has missing table name: left={left_table}, right={right_table}, columns={jc.left_column}, {jc.right_column}")
            
            # Convert table names in the join conditions to aliases
            converted_join_conditions = []
            for jc_str in all_join_conditions_set:
                # Replace table names with aliases (if not replaced yet)
                converted_jc = jc_str
                for table_name, alias in table_to_alias.items():
                    converted_jc = converted_jc.replace(f"{table_name}.", f"{alias}.")
                
                # Check that no invalid condition (of the form `.column`) remains after conversion
                if " ." in converted_jc or converted_jc.startswith("."):
                    logger.error(f"Invalid JOIN condition after conversion: {converted_jc} (original: {jc_str})")
                    continue  # skip invalid conditions
                
                converted_join_conditions.append(converted_jc)
            
            # Add the rest as comma joins (all join conditions go in the WHERE clause)
            for comp in flat_components:
                for i, table_info in enumerate(comp['tables']):
                    if comp == flat_components[0] and i == 0:
                        continue  # the first table was already added
                    
                    # Use comma joins and move all join conditions to the WHERE clause
                    # This lets the PostgreSQL query planner choose the best join order
                    from_parts.append(f", {table_info['source']} AS {table_info['alias']}")
            
            from_clause = " ".join(from_parts)  # comma joins, so no line breaks are needed
            
            # Build the SELECT clause: avoid duplicates based on the final output column names
            select_parts = []
            used_output_names = set()  # track the final output column names
            
            for comp in flat_components:
                for table_info in comp['tables']:
                    table_name = table_info['source']
                    alias = table_info['alias']
                    
                    # Get the columns of the table
                    columns = self._get_table_columns(table_name)
                    
                    if columns:
                        for col in columns:
                            base_name = col

                            # Prefer the original column name first
                            if base_name not in used_output_names:
                                select_parts.append(f"{alias}.{col}")
                                used_output_names.add(base_name)
                                continue

                            # On a collision, use alias_col as the base; if it still collides, append a sequence number
                            alias_base = f"{alias}_{col}"
                            candidate_name = alias_base
                            suffix = 2
                            while candidate_name in used_output_names:
                                candidate_name = f"{alias_base}_{suffix}"
                                suffix += 1

                            select_parts.append(f"{alias}.{col} AS {candidate_name}")
                            used_output_names.add(candidate_name)
                    else:
                        # Without schema information, select the whole table (qualified with the alias)
                        logger.warning(f"No schema info for {table_name}, using {alias}.*")
                        select_parts.append(f"{alias}.*")
            
            select_clause = ",\n    ".join(select_parts) if select_parts else "*"
            
            # Build the WHERE clause: include all join conditions and filters
            where_clause = ""
            where_conditions = converted_join_conditions + all_filters
            
            # Supplement join conditions from the original SQL (restores join conditions lost through PostgreSQL constant pushdown)
            all_aliases = set()
            for comp in flat_components:
                for table_info in comp['tables']:
                    all_aliases.add(table_info['alias'].lower())
            
            supplemented = self._supplement_missing_join_conditions(
                node_id, all_aliases, where_conditions
            )
            if supplemented:
                where_conditions.extend(supplemented)
            
            if where_conditions:
                where_clause = f"\nWHERE {' AND '.join(where_conditions)}"
            
            # Build final SQL
            sql = f"""CREATE MATERIALIZED VIEW {node_id} AS
SELECT {select_clause}
FROM {from_clause}{where_clause};"""
            
            return sql
        except Exception as e:
            logger.error(f"Error in _generate_non_leaf_mv_enhanced for {node_id}: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to old method
            return self._generate_non_leaf_mv_fallback(node_id)
    
    def _flatten_node(self, node_id: str) -> dict:
        """Recursively flatten a node into a list of tables/selected MVs.
        
        Args:
            node_id: Node ID
            
        Returns:
            {
                'tables': [{'source': table name or MV name, 'alias': alias}, ...],
                'join_conditions': [join condition string, ...],
                'filters': [filter condition string, ...]
            }
        """
        # Leaf node case
        if node_id in self.qm.leaf_nodes_map_r:
            
            # If not selected, expand it as a table
            operator, table, alias, filter_condition = self.qm.leaf_nodes_map_r[node_id]
            
            # Add the table alias to the filter condition
            fixed_filter = self._add_table_alias_to_filter(filter_condition, alias) if filter_condition else None
            
            result = {
                'tables': [{'source': table, 'alias': alias}],
                'join_conditions': [],
                'filters': [fixed_filter] if fixed_filter else []
            }
            return result
        
        # Non-leaf node case
        elif node_id in self.qm.non_leaf_nodes_info:
            # If it is a selected MV, treat it as a single table
            if node_id in self.selected_mvs:
                return {
                    'tables': [{'source': node_id, 'alias': node_id}],
                    'join_conditions': [],
                    'filters': []
                }
            
            # If not selected, expand it further
            node_info = self.qm.non_leaf_nodes_info[node_id]
            result = {
                'tables': [],
                'join_conditions': [],
                'filters': list(node_info.filters) if node_info.filters else []
            }
            
            # Recursively expand the child nodes
            for child_id in node_info.children:
                child_flat = self._flatten_node(child_id)
                result['tables'].extend(child_flat['tables'])
                result['join_conditions'].extend(child_flat['join_conditions'])
                result['filters'].extend(child_flat['filters'])
            
            # Add the join conditions of this node (deduplicated)
            if node_info.join_conditions:
                for jc in node_info.join_conditions:
                    jc_str = f"{jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}"
                    if jc_str not in result['join_conditions']:
                        result['join_conditions'].append(jc_str)
            
            return result
        
        else:
            logger.error(f"Node {node_id} not found")
            return {'tables': [], 'join_conditions': [], 'filters': []}
    
    def _add_table_alias_to_filter(self, filter_condition: str, table_alias: str) -> str:
        """Add the table alias to the column references in a filter condition.
        
        Args:
            filter_condition: Original filter condition (e.g., "((info)::text = 'top 250 rank'::text)")
            table_alias: Table alias (e.g., "it")
            
        Returns:
            Filter condition with the alias added (e.g., "((it.info)::text = 'top 250 rank'::text)")
        """
        if not filter_condition or not table_alias:
            return filter_condition
        
        import re

        # Exclude the inside of SQL string literals ('...') from replacement.
        # This prevents a value such as '(Berlin International Film Festival)'
        # from being broken into '(movie_info.Berlin International Film Festival)' by mistake.
        literal_pattern = re.compile(r"'(?:''|[^'])*'")

        def process_non_literal(segment: str) -> str:
            """Apply alias qualification only to non-literal SQL fragments."""
            if not segment:
                return segment
        
            # Detect the column reference pattern: the form (column_name)::
            # Skip if an alias is already attached (the form alias.column)
            def replace_column_cast(match):
                full_match = match.group(0)
                column_name = match.group(1)
                # Check whether an alias is already attached
                if '.' in column_name:
                    return full_match  # return as is
                # Add the alias: (column_name):: -> (alias.column_name)::
                return f"({table_alias}.{column_name})::"
        
            # Pattern 1: (column_name):: -> (alias.column_name)::
            result = re.sub(r'\((\w+)\)::', replace_column_cast, segment)
        
            # Pattern 2: bare column names used on their own, e.g. in the WHERE clause
            # e.g., "note = 'something'" -> "it.note = 'something'"
            # e.g., "note IS NULL" -> "it.note IS NULL"
            # e.g., "note IS NOT NULL" -> "it.note IS NOT NULL"
            # but exclude function names and names that already have an alias
        
            # List of SQL type keywords and reserved words (for cases such as ::double precision)
            SQL_TYPE_KEYWORDS = {
                'AND', 'OR', 'NOT', 'IN', 'ANY', 'ALL', 'NULL',
                'PRECISION', 'TIMESTAMP', 'INTEGER', 'VARCHAR', 'CHAR',
                'TEXT', 'BOOLEAN', 'FLOAT', 'DOUBLE', 'REAL', 'NUMERIC',
                'DATE', 'TIME', 'INTERVAL', 'ARRAY', 'JSON', 'JSONB',
                'WITH', 'WITHOUT', 'ZONE'
            }
        
            def replace_bare_column(match):
                prefix = match.group(1)  # preceding character (space or parenthesis)
                column_name = match.group(2)
                suffix = match.group(3)  # following characters (operator, etc.)

                # Skip if an alias is already attached, or if it is an SQL type keyword or possibly a function name
                if '.' in column_name or column_name.upper() in SQL_TYPE_KEYWORDS:
                    return match.group(0)

                return f"{prefix}{table_alias}.{column_name}{suffix}"
        
            # Detect column names delimited by word boundaries (e.g., before an operator)
            # Also handle the IS NOT NULL and IS NULL patterns
            # (?<![.]) checks that the preceding character is not a dot
            # Match only identifiers starting with [a-zA-Z_] (excludes numeric literals)
            result = re.sub(
                r'(\s|\(|^)([a-zA-Z_][a-zA-Z0-9_]*)(?!\s*\.)(\s*(?:(?:IS\s+NOT\s+NULL|IS\s+NULL)\b|(?:ILIKE|LIKE|IN|ANY)\b|!=|<=|>=|=|<|>|~|!~))',
                replace_bare_column,
                result,
                flags=re.IGNORECASE,
            )
        
            # Also handle column names after an operator (e.g., "1928 < production_year")
            def replace_bare_column_after_op(match):
                op = match.group(1)  # operator
                space = match.group(2)  # whitespace
                column_name = match.group(3)

                # Skip if an alias is already attached, or if it is an SQL type keyword or possibly a function name
                if '.' in column_name or column_name.upper() in SQL_TYPE_KEYWORDS:
                    return match.group(0)

                return f"{op}{space}{table_alias}.{column_name}"
        
            # Detect column names after an operator (e.g., "< production_year", "> age")
            result = re.sub(
                r'(=|!=|<=|>=|<|>|~|!~)(\s+)([a-zA-Z_][a-zA-Z0-9_]*)(?!\s*\.)\b',
                replace_bare_column_after_op,
                result,
                flags=re.IGNORECASE,
            )

            escaped_alias = re.escape(table_alias)
            result = re.sub(rf'\b{escaped_alias}\.{escaped_alias}\.', f'{table_alias}.', result)

            return result

        out = []
        last = 0
        for match in literal_pattern.finditer(filter_condition):
            out.append(process_non_literal(filter_condition[last:match.start()]))
            out.append(match.group(0))
            last = match.end()
        out.append(process_non_literal(filter_condition[last:]))

        return ''.join(out)
    
    def _collect_all_join_conditions(self, node_info: NonLeafNodeInfo, qm: Any) -> list[JoinCondition]:
        """Recursively collect all join conditions from the whole subtree.
        
        Args:
            node_info: Information of the current node
            qm: QueryManager instance
            
        Returns:
            List of all join conditions in the subtree
        """
        all_conditions = []
        
        # Add the join conditions of the current node
        if node_info.join_conditions:
            all_conditions.extend(node_info.join_conditions)
        
        # If a child node is non_leaf, collect recursively
        for child in node_info.children:
            # Get the child node ID
            child_node_id = None
            
            # child is a string
            if isinstance(child, str):
                child_node_id = child
            # child is an object
            elif hasattr(child, 'node_id'):
                child_node_id = child.node_id
            elif hasattr(child, 'id'):
                child_node_id = child.id
            
            # Recurse only for non_leaf child nodes
            if child_node_id and child_node_id.startswith('non_leaf_'):
                if child_node_id in qm.non_leaf_nodes_info:
                    child_node = qm.non_leaf_nodes_info[child_node_id]
                    # Recursively collect the join conditions of the child node
                    all_conditions.extend(
                        self._collect_all_join_conditions(child_node, qm)
                    )
        
        return all_conditions

    def _supplement_missing_join_conditions(
        self,
        node_id: str,
        all_aliases: set[str],
        existing_conditions: list[str]
    ) -> list[str]:
        """Detect unjoined tables and supplement join conditions from the original SQL.

        Join conditions that disappeared from the execution plan due to PostgreSQL
        constant pushdown are recovered from the original SQL query.

        Args:
            node_id: Node ID
            all_aliases: All aliases in the FROM clause (lowercase)
            existing_conditions: List of existing WHERE clause conditions

        Returns:
            List of join condition strings to add
        """
        if not self.query_parser or not hasattr(self.qm, 'original_query_join_conditions'):
            return []

        if not self.qm.original_query_join_conditions:
            return []

        # Detect the aliases that the existing conditions link to another alias through a comparison
        # Single-table filters (e.g., t.id = 10) do not count as covered
        covered_aliases = set()
        for cond in existing_conditions:
            covered_aliases.update(self._extract_linked_aliases_from_condition(cond))

        # Unjoined aliases = in the FROM clause but not linked by any WHERE clause condition
        unjoined_aliases = all_aliases - covered_aliases

        if not unjoined_aliases:
            return []  # all joined

        logger.info(f"Node {node_id}: unjoined aliases detected: {unjoined_aliases}")

        # Identify the queries this node belongs to
        query_indices = self._find_queries_for_node(node_id)

        if not query_indices:
            logger.warning(f"Node {node_id}: cannot find parent query for unjoined alias supplementation")
            return []

        # Get the join conditions involving those aliases from the original SQL
        supplemented = []
        supplemented_set = set()  # deduplication

        for qi in query_indices:
            if qi not in self.qm.original_query_join_conditions:
                continue

            for la, lc, ra, rc in self.qm.original_query_join_conditions[qi]:
                # Supplement when both sides are aliases in this subtree
                # and at least one of them is an unjoined alias
                if la in all_aliases and ra in all_aliases:
                    if la in unjoined_aliases or ra in unjoined_aliases:
                        cond_str = f"{la}.{lc} = {ra}.{rc}"
                        if cond_str not in supplemented_set:
                            supplemented_set.add(cond_str)
                            supplemented.append(cond_str)
                            logger.info(f"  Supplemented: {cond_str}")

            if supplemented:
                break  # the conditions of the first matching query are sufficient

        return supplemented

    @staticmethod
    def _normalize_identifier(token: str) -> str:
        """Normalize an identifier (strip double quotes + lowercase)."""
        token = token.strip()
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            token = token[1:-1]
        return token.lower()

    @classmethod
    def _extract_aliases_from_sql_expression(cls, expr: str) -> set[str]:
        """Extract the aliases of alias.column references from an SQL expression."""
        if not expr:
            return set()

        ident = r'(?:"[^"]+"|[a-zA-Z_][a-zA-Z0-9_]*)'
        alias_ref_pattern = re.compile(
            rf'({ident})\s*\.\s*({ident})',
            flags=re.IGNORECASE,
        )

        aliases = set()
        for match in alias_ref_pattern.finditer(expr):
            aliases.add(cls._normalize_identifier(match.group(1)))
        return aliases

    @classmethod
    def _extract_linked_aliases_from_condition(cls, condition: str) -> set[str]:
        """Extract only the aliases that reference each other through a comparison in a condition.

        - Excludes single-table filters such as `t.id = 10`
        - Targets `t1.c1 = t2.c2`, `t1.ts > t2.ts`, `UPPER(t1.n)=UPPER(t2.n)`, etc.
        """
        if not condition:
            return set()

        linked_aliases = set()

        # Even for compound expressions with OR/AND, decide per predicate
        predicates = re.split(r'\bAND\b|\bOR\b', condition, flags=re.IGNORECASE)

        # Comparison operators (longer tokens are matched first)
        comparison_pattern = re.compile(
            r'\bIS\s+NOT\s+DISTINCT\s+FROM\b|\bIS\s+DISTINCT\s+FROM\b|!=|<>|<=|>=|=|<|>',
            flags=re.IGNORECASE,
        )

        for predicate in predicates:
            pred = predicate.strip()
            if not pred:
                continue

            op_match = comparison_pattern.search(pred)
            if not op_match:
                continue

            left_expr = pred[:op_match.start()].strip()
            right_expr = pred[op_match.end():].strip()

            left_aliases = cls._extract_aliases_from_sql_expression(left_expr)
            right_aliases = cls._extract_aliases_from_sql_expression(right_expr)

            # Treat as covered only when different aliases are involved on the two sides of the comparison
            if left_aliases and right_aliases:
                involved = left_aliases | right_aliases
                if len(involved) >= 2:
                    linked_aliases.update(involved)

        return linked_aliases

    def _find_queries_for_node(self, node_id: str) -> list[int]:
        """Return the list of indices of the queries a node belongs to.

        Args:
            node_id: Node ID

        Returns:
            List of query indices
        """
        positions = self.qm.subquery_positions.get(node_id, [])
        if positions:
            return list(set(pos[0] for pos in positions if pos[0] >= 0))

        # If there are no positions, infer from the child nodes
        if node_id in self.qm.non_leaf_nodes_info:
            node_info = self.qm.non_leaf_nodes_info[node_id]
            for child_id in node_info.children:
                child_queries = self._find_queries_for_node(child_id)
                if child_queries:
                    return child_queries

        return []
    
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
            from src.rewrite.schema import get_table_columns
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
