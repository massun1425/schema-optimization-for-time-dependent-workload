"""Query rewriting logic"""

import os
import re
from pathlib import Path
from typing import Any
import logging

from src.rewrite.mv_generator import MVGenerator
from src.rewrite.sql_parser import SQLParser
from src.rewrite.join_graph import JoinGraph, JoinMinimizer
from src.utils.legacy import natural_sort_key
import sqlparse
from sqlparse.sql import Where, TokenList

logger = logging.getLogger(__name__)


class QueryRewriter:
    """Manages query rewriting"""

    def __init__(self, query_manager: Any = None, containment_matrix: list = None, node_list: list = None, query_set: str = "job"):
        """Initialize

        Args:
            query_manager: Query management object or Settings
            containment_matrix: X matrix (containment relation). X[i][j]=1 means node i contains node j
            node_list: List of node IDs (corresponding to the indices of the X matrix)
            query_set: Query set name (job if not specified)
        """
        # Handle the case where a settings object is passed
        if hasattr(query_manager, 'database'):
            # This is a Settings object
            self.settings = query_manager
            self.qm = None
        else:
            # This is a QueryManager object
            self.qm = query_manager
            self.settings = None
        
        # Containment matrix (used to remove redundant MVs)
        self.containment_matrix = containment_matrix
        self.node_list = node_list
        self.query_set = query_set or "job"
        if containment_matrix is not None and node_list is not None:
            self._node_to_idx = {node_id: idx for idx, node_id in enumerate(node_list)}
            logger.info(f"Containment matrix enabled: {len(node_list)} nodes")
        else:
            self._node_to_idx = {}
            logger.debug("Containment matrix not provided - redundant MV filtering disabled")
        
        self.sql_parser = SQLParser()
        self.mv_generator = MVGenerator()

    def _get_query_dir(self) -> Path:
        """Resolve the directory of the queries to be rewritten

        For backward compatibility, job is used when query_set is not specified.
        """
        if self.settings:
            base_dir = Path(self.settings.benchmark.sql_dir)
            target_dir = base_dir / self.query_set
            if target_dir.exists():
                return target_dir
            return base_dir / "job"

        return Path("dataset/RED_SQL/job")
    
    def rewrite_queries(self, selected_views: list) -> dict[str, str]:
        """Rewrite queries using the selected MVs
        
        Args:
            selected_views: List of selected materialized views
                          Each element is a dict {'view_id': str, 'node_id': str, 'create_sql': str, 
                                    'usage_positions': [[query_num, position], ...]}
            
        Returns:
            Dict of {query_id: rewritten_sql}
        """
        logger.info(f"Starting query rewriting with {len(selected_views)} selected views")
        
        # Map each query to the MVs it uses
        query_to_mvs = self._build_query_mv_mapping(selected_views)
        
        # Get the path of the original query files
        query_dir = self._get_query_dir()
        
        rewritten = {}
        
        # Process each query (sorted with the same natural_sort_key as the optimization phase)
        for query_file in sorted(query_dir.glob("*.sql"), key=lambda x: natural_sort_key(str(x))):
            query_id = query_file.stem  # file name without the extension (e.g., "1a")
            
            # If no MV is used for this query, use the original query as is
            if query_id not in query_to_mvs or not query_to_mvs[query_id]:
                with open(query_file, 'r') as f:
                    rewritten[query_id] = f.read()
                continue
            
            # Rewrite the query
            try:
                rewritten_sql = self._rewrite_single_query(
                    query_file, 
                    query_to_mvs[query_id]
                )
                rewritten[query_id] = rewritten_sql
                logger.debug(f"Successfully rewrote query {query_id}")
            except Exception as e:
                logger.error(f"Error rewriting query {query_id}: {e}")
                # On error, use the original query
                with open(query_file, 'r') as f:
                    rewritten[query_id] = f.read()
        
        logger.info(f"Completed query rewriting for {len(rewritten)} queries")
        return rewritten
    
    def _build_query_mv_mapping(self, selected_views: list) -> dict[str, list]:
        """Build the mapping from each query to the MVs it uses from selected_views
        
        Args:
            selected_views: List of selected materialized views (MaterializedView objects)
            
        Returns:
            Dict of {query_id: [MaterializedView, ...]}
        """
        # Build the mapping from query number (0-based) to file name
        # Use the same natural_sort_key as the optimization phase
        query_dir = self._get_query_dir()
        
        # Use the same sort order as the optimization phase (natural_sort_key)
        query_files = sorted(query_dir.glob("*.sql"), key=lambda x: natural_sort_key(str(x)))
        query_num_to_id = {i: f.stem for i, f in enumerate(query_files)}
        
        logger.debug(f"Built query number to ID mapping for {len(query_num_to_id)} queries")
        if logger.isEnabledFor(logging.DEBUG):
            # Log the first 10 mappings
            for i in range(min(10, len(query_num_to_id))):
                logger.debug(f"  Query {i}: {query_num_to_id[i]}")
        
        query_to_mvs = {}
        
        for mv in selected_views:
            # MaterializedView object
            if hasattr(mv, 'usage_positions'):
                usage_positions = mv.usage_positions
            # dict (backward compatibility)
            elif isinstance(mv, dict) and 'usage_positions' in mv:
                usage_positions = mv['usage_positions']
            else:
                continue
                
            for position in usage_positions:
                query_num = position[0]  # query number (0-based: 0-112)
                
                # Convert the query number to the query ID
                if query_num not in query_num_to_id:
                    logger.warning(f"Query number {query_num} not found in mapping")
                    continue
                
                query_id = query_num_to_id[query_num]
                
                if query_id not in query_to_mvs:
                    query_to_mvs[query_id] = []
                
                query_to_mvs[query_id].append(mv)
        
        # Remove redundant MVs using the containment matrix
        if self.containment_matrix is not None and self._node_to_idx:
            query_to_mvs = self._filter_redundant_mvs(query_to_mvs)
        
        return query_to_mvs
    
    def _filter_redundant_mvs(self, query_to_mvs: dict) -> dict:
        """Remove redundant MVs using the containment matrix
        
        If MV A contains MV B (X[A][B]=1), MV B is redundant and is removed.
        
        Args:
            query_to_mvs: Mapping {query_id: [MV, ...]}
            
        Returns:
            Mapping after removing redundant MVs
        """
        filtered = {}
        total_removed = 0
        
        for query_id, mvs in query_to_mvs.items():
            if len(mvs) <= 1:
                filtered[query_id] = mvs
                continue
            
            # Get the node_id of each MV
            mv_node_ids = []
            for mv in mvs:
                if hasattr(mv, 'node_id'):
                    node_id = mv.node_id
                elif isinstance(mv, dict):
                    node_id = mv.get('node_id', '')
                else:
                    node_id = ''
                mv_node_ids.append(node_id)
            
            # Identify redundant MVs (those contained in another MV)
            redundant_indices = set()
            for i, node_i in enumerate(mv_node_ids):
                for j, node_j in enumerate(mv_node_ids):
                    if i == j:
                        continue
                    idx_i = self._node_to_idx.get(node_i)
                    idx_j = self._node_to_idx.get(node_j)
                    if idx_i is not None and idx_j is not None:
                        # X[i][j]=1 means node i contains node j
                        if self.containment_matrix[idx_i][idx_j] == 1:
                            redundant_indices.add(j)
                            logger.debug(f"Query {query_id}: {node_i} contains {node_j} - removing {node_j}")
            
            # Keep only the non-redundant MVs
            non_redundant_mvs = [mv for k, mv in enumerate(mvs) if k not in redundant_indices]
            filtered[query_id] = non_redundant_mvs
            total_removed += len(redundant_indices)
        
        if total_removed > 0:
            logger.info(f"Removed {total_removed} redundant MVs using containment matrix")
        
        return filtered
    
    def _rewrite_single_query(self, query_file: Path, mvs: list) -> str:
        """Rewrite a single query using MVs
        
        Args:
            query_file: Path of the original query file
            mvs: List of MVs used for this query
            
        Returns:
            The rewritten SQL statement
        """
        # Read the original query
        with open(query_file, 'r') as f:
            original_sql = f.read()
        
        # Normalize the SQL
        sql = self._normalize_sql(original_sql)
        
        # Split the SQL into its components
        parts = self._parse_sql_parts(sql)
        
        # Apply each MV
        for mv in mvs:
            parts = self._apply_mv_to_query(parts, mv)
        
        # Reconstruct the rewritten SQL
        rewritten_sql = self._reconstruct_sql(parts)
        
        return rewritten_sql
    
    def _normalize_sql(self, sql: str) -> str:
        """Normalize SQL (unify spaces, line breaks, letter case, etc.)
        
        Args:
            sql: Original SQL statement
            
        Returns:
            The normalized SQL statement
        """
        # Step 1: protect string literals (temporarily replace them with placeholders)
        string_literals = []
        
        def replace_literal(match):
            """Replace a string literal with a placeholder"""
            literal = match.group(0)
            placeholder = f"__STRING_LITERAL_{len(string_literals)}__"
            string_literals.append(literal)
            return placeholder
        
        # Handle both single and double quotes (including escapes)
        # Pattern: a string enclosed in ' or a string enclosed in "
        sql = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", replace_literal, sql)
        
        # Step 2: normalize the SQL (safe because string literals are protected)
        # Line breaks to spaces
        sql = sql.replace('\n', ' ')
        
        # Collapse multiple spaces into one
        sql = re.sub(r'\s+', ' ', sql)
        
        # Uppercase keywords (string literals are already placeholders and are not affected)
        sql = re.sub(r'\bas\b', 'AS', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\band\b', 'AND', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bor\b', 'OR', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\blike\b', 'LIKE', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bnot\b', 'NOT', sql, flags=re.IGNORECASE)
        sql = re.sub(r'\bin\b', 'IN', sql, flags=re.IGNORECASE)
        
        # Spaces around operators
        sql = re.sub(r'(?<! )=(?! )', ' = ', sql)
        sql = sql.replace('! =', '!=')
        
        # Step 3: restore the string literals
        for i, literal in enumerate(string_literals):
            placeholder = f"__STRING_LITERAL_{i}__"
            sql = sql.replace(placeholder, literal)
        
        return sql.strip()

    
    def _parse_sql_parts(self, sql: str) -> dict:
        """Split SQL into its components
        
        Args:
            sql: SQL statement
            
        Returns:
            Dict of {'select': str, 'from': str, 'where': str, 'group_by': str}
        """
        parts = {
            'select': '',
            'from': '',
            'where': '',
            'group_by': ''
        }

        def join_token_values(token_slice) -> str:
            return ' '.join(t.value.strip() for t in token_slice if t.value and t.value.strip())

        # Determine clause boundaries with sqlparse (does not mistake a ; inside a string literal)
        parsed = sqlparse.parse(sql)
        if parsed:
            stmt = parsed[0]
            tokens = [t for t in stmt.tokens if not t.is_whitespace]

            def is_boundary_keyword(token) -> bool:
                if token.ttype is None:
                    return False
                if token.ttype.parent != sqlparse.tokens.Keyword and token.ttype != sqlparse.tokens.Keyword:
                    return False
                return token.normalized in {
                    'WHERE', 'GROUP BY', 'ORDER BY', 'HAVING',
                    'LIMIT', 'UNION', 'EXCEPT', 'INTERSECT'
                }

            select_idx = None
            from_idx = None
            for i, token in enumerate(tokens):
                if token.ttype == sqlparse.tokens.DML and token.normalized == 'SELECT':
                    select_idx = i
                    break

            if select_idx is not None:
                for i in range(select_idx + 1, len(tokens)):
                    token = tokens[i]
                    if token.ttype == sqlparse.tokens.Keyword and token.normalized == 'FROM':
                        from_idx = i
                        break

            if select_idx is not None and from_idx is not None and from_idx > select_idx:
                parts['select'] = join_token_values(tokens[select_idx + 1:from_idx]).strip()
                # Fix up: joining sqlparse tokens can collapse DISTINCT ON into DISTINCTON
                parts['select'] = re.sub(r'\bDISTINCT\s*ON\b', 'DISTINCT ON', parts['select'], flags=re.IGNORECASE)

            if from_idx is not None:
                from_end = len(tokens)
                for i in range(from_idx + 1, len(tokens)):
                    token = tokens[i]
                    if isinstance(token, Where) or is_boundary_keyword(token) or token.value == ';':
                        from_end = i
                        break
                parts['from'] = join_token_values(tokens[from_idx + 1:from_end]).strip()

            where_token = None
            for token in tokens:
                if isinstance(token, Where):
                    where_token = token
                    break

            if where_token is not None:
                where_text = where_token.value
                parts['where'] = re.sub(r'^\s*WHERE\s+', '', where_text, flags=re.IGNORECASE).strip().rstrip(';').strip()

            group_idx = None
            for i, token in enumerate(tokens):
                if token.ttype == sqlparse.tokens.Keyword and token.normalized == 'GROUP BY':
                    group_idx = i
                    break

            if group_idx is not None:
                group_end = len(tokens)
                for i in range(group_idx + 1, len(tokens)):
                    token = tokens[i]
                    if (token.ttype == sqlparse.tokens.Keyword and token.normalized in {'ORDER BY', 'LIMIT', 'UNION', 'EXCEPT', 'INTERSECT'}) or token.value == ';':
                        group_end = i
                        break
                parts['group_by'] = join_token_values(tokens[group_idx + 1:group_end]).strip()

        # Fallback when sqlparse could not extract the parts
        if not parts['select'] or not parts['from']:
            select_match = re.search(r'SELECT\s+(.+?)\s+FROM\s+', sql, re.IGNORECASE | re.DOTALL)
            if not select_match:
                select_match = re.search(r'SELECT\s+(.+?)\sFROM\s', sql, re.IGNORECASE | re.DOTALL)
            if select_match and not parts['select']:
                parts['select'] = select_match.group(1).strip()

            from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|\s+GROUP\s+BY|$)', sql, re.IGNORECASE | re.DOTALL)
            if from_match and not parts['from']:
                parts['from'] = from_match.group(1).strip().rstrip(';').strip()

            where_match = re.search(r'WHERE\s+(.+?)(?:\s+GROUP\s+BY|$)', sql, re.IGNORECASE | re.DOTALL)
            if where_match and not parts['where']:
                parts['where'] = where_match.group(1).strip().rstrip(';').strip()

            group_match = re.search(r'GROUP\s+BY\s+(.+?)(?:\s+ORDER\s+BY|$)', sql, re.IGNORECASE | re.DOTALL)
            if group_match and not parts['group_by']:
                parts['group_by'] = group_match.group(1).strip().rstrip(';').strip()

        # Flatten JOIN ... ON into a form that is easier to process internally
        if re.search(r'\bJOIN\b', parts['from'], re.IGNORECASE):
            flattened_from, join_conditions = self._flatten_join_from_clause(parts['from'])
            if flattened_from:
                parts['from'] = flattened_from
            if join_conditions:
                join_where = ' AND '.join(join_conditions)
                if parts['where']:
                    parts['where'] = f"{join_where} AND {parts['where']}"
                else:
                    parts['where'] = join_where
        
        return parts

    def _normalize_identifier_token(self, token: str) -> str:
        token = token.strip()
        if token.startswith('"') and token.endswith('"') and len(token) >= 2:
            return token[1:-1]
        return token

    def _parse_table_expr(self, expr: str) -> tuple[str, str]:
        """Extract table_name and alias from a table expression"""
        expr = expr.strip()
        match = re.match(
            r'^("?[A-Za-z_][A-Za-z0-9_]*"?)\s*(?:AS\s+)?("?[A-Za-z_][A-Za-z0-9_]*"?)?$',
            expr,
            re.IGNORECASE,
        )
        if not match:
            normalized = self._normalize_identifier_token(expr)
            return normalized, normalized

        table_name = self._normalize_identifier_token(match.group(1))
        alias_token = match.group(2)
        alias = self._normalize_identifier_token(alias_token) if alias_token else table_name
        return table_name, alias

    def _flatten_join_from_clause(self, from_clause: str) -> tuple[str, list[str]]:
        """Flatten JOIN ... ON into comma-separated tables + WHERE conditions"""
        clause = from_clause.strip()
        join_match = re.search(r'\bJOIN\b', clause, re.IGNORECASE)
        if not join_match:
            return clause, []

        first_table_expr = clause[:join_match.start()].strip()
        table_exprs = [first_table_expr] if first_table_expr else []
        join_conditions: list[str] = []

        for match in re.finditer(
            r'\bJOIN\b\s+(.+?)\s+\bON\b\s+(.+?)(?=\s+\bJOIN\b\s+|$)',
            clause,
            re.IGNORECASE | re.DOTALL,
        ):
            table_expr = match.group(1).strip()
            condition = match.group(2).strip()
            if table_expr:
                table_exprs.append(table_expr)
            if condition:
                join_conditions.append(condition)

        normalized_table_exprs = []
        for expr in table_exprs:
            table_name, alias = self._parse_table_expr(expr)
            normalized_table_exprs.append(f'{table_name} AS {alias}')

        return ', '.join(normalized_table_exprs), join_conditions
    
    def _apply_mv_to_query(self, parts: dict, mv: dict) -> dict:
        """Apply an MV and rewrite the query components (graph-based minimization)
        
        Args:
            parts: Query components
            mv: MV to apply (MaterializedView object or dict)
            
        Returns:
            The rewritten components
        """
        # Get the attributes from the MaterializedView object or dict
        if hasattr(mv, 'view_id'):
            view_id = mv.view_id
            create_sql = mv.create_sql
        elif isinstance(mv, dict):
            view_id = mv.get('view_id', '')
            create_sql = mv.get('create_sql', '')
        else:
            logger.warning(f"Unknown MV type: {type(mv)}")
            return parts
        
        # Remove the "mv_" prefix from view_id (to match the actual MV name in the database)
        if view_id.startswith('mv_'):
            view_id = view_id[3:]  # remove "mv_"
        
        logger.info(f"Applying MV: {view_id}")
        
        # Analyze the MV definition
        mv_parts = self._analyze_mv_definition(create_sql)
        
        if not mv_parts:
            logger.warning(f"Could not analyze MV definition for {view_id}")
            return parts
        
        # Get the tables and aliases of the MV
        mv_tables = self._extract_tables_from_from_clause(mv_parts['from'])
        mv_table_mappings = self._extract_table_mappings_from_from_clause(mv_parts['from'])
        
        logger.debug(f"MV contains tables: {mv_tables}")
        
        # Query-side table name -> alias mapping
        query_table_mappings = self._extract_table_mappings_from_from_clause(parts['from'])
        
        # Build the alias -> column name mapping from the SELECT clause of the MV
        alias_to_column_mapping = self._extract_mv_column_mapping(mv_parts.get('select', ''), mv_tables)
        
        # ===== STEP 1: classify the WHERE clause into join conditions and filter conditions =====
        minimizer = JoinMinimizer()
        join_conditions, filter_conditions = minimizer.classify_conditions(parts['where'])
        
        logger.debug(f"Original: {len(join_conditions)} joins, {len(filter_conditions)} filters")
        
        # ===== STEP 2: remove the join conditions internal to the MV =====
        external_joins = []
        for join_cond in join_conditions:
            involved_tables = self._extract_tables_from_condition(join_cond, query_table_mappings)
            
            # Both tables are contained in the MV -> it is an MV-internal join, so remove it
            if len(involved_tables) == 2 and all(table in mv_tables for table in involved_tables):
                logger.debug(f"Removing MV internal join: {join_cond}")
                continue
            
            external_joins.append(join_cond)
        
        logger.debug(f"After removing MV internal joins: {len(external_joins)} joins")
        
        # ===== STEP 3: rewrite the FROM clause (replace the MV's tables with the MV) =====
        parts['from'] = self._replace_tables_with_mv(parts['from'], mv_tables, view_id)
        
        # ===== STEP 4: update alias references in the SELECT and WHERE clauses =====
        logger.debug(f"Updating aliases with mapping: {alias_to_column_mapping}")
        
        for old_ref, new_column in alias_to_column_mapping.items():
            alias, column = old_ref.split('.', 1)
            replacement = f"{view_id}.{new_column}"

            patterns = [
                r'\b' + re.escape(old_ref) + r'\b',
                r'"' + re.escape(alias) + r'"\."' + re.escape(column) + r'"',
            ]

            for pattern in patterns:
                # Update the SELECT clause
                parts['select'] = re.sub(pattern, replacement, parts['select'])

                # Update the join conditions of the WHERE clause
                updated_joins = []
                for join_cond in external_joins:
                    updated_joins.append(re.sub(pattern, replacement, join_cond))
                external_joins = updated_joins

                # Also update the filter conditions
                updated_filters = []
                for filter_cond in filter_conditions:
                    updated_filters.append(re.sub(pattern, replacement, filter_cond))
                filter_conditions = updated_filters

                # Update the GROUP BY clause
                if parts['group_by']:
                    parts['group_by'] = re.sub(pattern, replacement, parts['group_by'])
        
        # ===== STEP 5: remove filter conditions contained in the MV =====
        if mv_parts['where']:
            mv_filter_conds = self._extract_conditions(mv_parts['where'])
            normalized_mv_conds = [
                self._normalize_condition_for_comparison(c, mv_table_mappings) 
                for c in mv_filter_conds
            ]
            
            remaining_filters = []
            for cond in filter_conditions:
                normalized = self._normalize_condition_for_comparison(cond, query_table_mappings)
                if normalized not in normalized_mv_conds:
                    remaining_filters.append(cond)
                else:
                    logger.debug(f"Removing filter covered by MV: {cond}")
            
            filter_conditions = remaining_filters
        
        # ===== STEP 6: remove redundant join conditions using the join graph =====
        minimal_joins, _ = minimizer.minimize_joins(external_joins, filter_conditions)
        
        logger.info(f"Join minimization: {len(external_joins)} → {len(minimal_joins)}")
        
        # ===== STEP 7: reconstruct the WHERE clause =====
        all_conditions = minimal_joins + filter_conditions
        parts['where'] = ' AND '.join(all_conditions) if all_conditions else ''
        
        logger.debug(f"Final WHERE ({len(all_conditions)} conditions): {parts['where'][:200]}...")
        
        return parts
    
    def _extract_mv_column_mapping(self, select_clause: str, mv_tables: list[str]) -> dict[str, str]:
        """Extract the alias.column -> MV column name mapping from the SELECT clause of the MV
        
        Args:
            select_clause: SELECT clause of the MV
            mv_tables: List of aliases of the tables contained in the MV
            
        Returns:
            Dict of {original alias.column: MV column name}
            e.g. {'it.id': 'it_id', 'mi_idx.movie_id': 'movie_id'}
        """
        mapping = {}
        
        # Parse each column of the SELECT clause
        # Remove line breaks before processing
        select_clause = select_clause.replace('\n', ' ')
        select_clause = re.sub(r'\s+', ' ', select_clause)
        
        columns = select_clause.split(',')
        for col in columns:
            col = col.strip()
            
            # Detect the pattern alias.column_name [AS other_name]
            match = re.match(
                r'("?[A-Za-z_][A-Za-z0-9_]*"?)\.("?[A-Za-z_][A-Za-z0-9_]*"?)(?:\s+AS\s+("?[A-Za-z_][A-Za-z0-9_]*"?))?',
                col,
                re.IGNORECASE,
            )
            if match:
                alias = self._normalize_identifier_token(match.group(1))
                column = self._normalize_identifier_token(match.group(2))
                as_name = self._normalize_identifier_token(match.group(3)) if match.group(3) else column
                
                # Only aliases of tables contained in the MV
                if alias in mv_tables:
                    # The original alias.column becomes as_name in the MV
                    mapping[f"{alias}.{column}"] = as_name
        
        return mapping
    
    def _analyze_mv_definition(self, create_sql: str) -> dict:
        """Extract the SELECT, FROM and WHERE clauses from an MV definition
        
        Args:
            create_sql: CREATE MATERIALIZED VIEW statement
            
        Returns:
            Dict of {'select': str, 'from': str, 'where': str}, or None on failure
        """
        # Extract the CREATE MATERIALIZED VIEW ... AS SELECT ... part
        # Format: CREATE MATERIALIZED VIEW view_name AS\nSELECT ...\nFROM ...\nWHERE ...;
        
        try:
            # Extract the SELECT statement after AS
            as_match = re.search(r'AS\s+(SELECT.+)', create_sql, re.IGNORECASE | re.DOTALL)
            if not as_match:
                return None
            
            select_sql = as_match.group(1).strip()
            
            # Remove the semicolon
            if select_sql.endswith(';'):
                select_sql = select_sql[:-1]
            
            # Extract the SELECT clause
            select_match = re.search(r'SELECT\s+(.+?)\s+FROM', select_sql, re.IGNORECASE | re.DOTALL)
            select_clause = select_match.group(1).strip() if select_match else ''
            
            # Extract the FROM clause
            from_match = re.search(r'FROM\s+(.+?)(?:\s+WHERE|$)', select_sql, re.IGNORECASE | re.DOTALL)
            from_clause = from_match.group(1).strip() if from_match else ''
            
            # Extract the WHERE clause
            where_match = re.search(r'WHERE\s+(.+)$', select_sql, re.IGNORECASE | re.DOTALL)
            where_clause = where_match.group(1).strip() if where_match else ''
            
            return {
                'select': select_clause,
                'from': from_clause,
                'where': where_clause
            }
        except Exception as e:
            logger.error(f"Error analyzing MV definition: {e}")
            return None
    
    def _extract_tables_from_from_clause(self, from_clause: str) -> list[str]:
        """Extract the list of table aliases from the FROM clause
        
        Args:
            from_clause: FROM clause string
            
        Returns:
            List of aliases
        """
        aliases = []

        for table_match in re.finditer(
            r'(?:^|\bJOIN\b|,)\s*("?[A-Za-z_][A-Za-z0-9_]*"?(?:\s+(?:AS\s+)?"?[A-Za-z_][A-Za-z0-9_]*"?)?)',
            from_clause,
            re.IGNORECASE,
        ):
            expr = table_match.group(1).strip()
            _, alias = self._parse_table_expr(expr)
            aliases.append(alias)

        return aliases
    
    def _extract_table_mappings_from_from_clause(self, from_clause: str) -> dict[str, str]:
        """Extract the table name -> alias mapping from the FROM clause
        
        Args:
            from_clause: FROM clause string
            
        Returns:
            Dict of {table_name: alias}
        """
        mappings = {}

        for table_match in re.finditer(
            r'(?:^|\bJOIN\b|,)\s*("?[A-Za-z_][A-Za-z0-9_]*"?(?:\s+(?:AS\s+)?"?[A-Za-z_][A-Za-z0-9_]*"?)?)',
            from_clause,
            re.IGNORECASE,
        ):
            expr = table_match.group(1).strip()
            table_name, alias = self._parse_table_expr(expr)
            mappings[table_name] = alias

        return mappings
    
    def _replace_tables_with_mv(self, from_clause: str, mv_tables: list[str], view_id: str) -> str:
        """Replace tables in the FROM clause with the MV
        
        Args:
            from_clause: Original FROM clause
            mv_tables: List of aliases of the tables contained in the MV
            view_id: View ID of the MV
            
        Returns:
            The rewritten FROM clause
        """
        tables = [t.strip() for t in from_clause.split(',') if t.strip()]
        new_tables = []
        mv_added = False
        
        for table_expr in tables:
            _, alias = self._parse_table_expr(table_expr)
            if alias in mv_tables:
                # Replace the first MV table with the MV
                if not mv_added:
                    new_tables.append(view_id)
                    mv_added = True
                # Skip the other MV tables
                continue

            # Keep tables not contained in the MV as is
            new_tables.append(table_expr)
        
        return ', '.join(new_tables)
    
    def _remove_common_conditions(
        self, 
        original_where: str, 
        mv_where: str, 
        mv_table_mappings: dict[str, str],
        query_table_mappings: dict[str, str]
    ) -> str:
        """Remove conditions contained in the MV from the WHERE clause
        
        Args:
            original_where: WHERE clause of the original query
            mv_where: WHERE clause of the MV
            mv_table_mappings: Table name -> alias mapping of the MV (e.g. {'company_name': 'cn'})
            query_table_mappings: Table name -> alias mapping of the query
            
        Returns:
            The rewritten WHERE clause
        """
        # Split the WHERE conditions into individual conditions
        original_conds = self._extract_conditions(original_where)
        mv_conds = self._extract_conditions(mv_where)
        
        logger.debug(f"Original conditions: {original_conds}")
        logger.debug(f"MV conditions: {mv_conds}")
        logger.debug(f"MV table mappings: {mv_table_mappings}")
        logger.debug(f"Query table mappings: {query_table_mappings}")
        
        # Normalize the MV conditions (strip aliases so that they can be compared)
        normalized_mv_conds = []
        for mv_cond in mv_conds:
            normalized_mv_conds.append(self._normalize_condition_for_comparison(mv_cond, mv_table_mappings))
        
        # Remove the common conditions
        unique_conds = []
        for cond in original_conds:
            # Normalize and compare
            normalized_cond = self._normalize_condition_for_comparison(cond, query_table_mappings)
            
            # Compare with the MV conditions
            is_common = False
            for i, norm_mv_cond in enumerate(normalized_mv_conds):
                if normalized_cond == norm_mv_cond:
                    is_common = True
                    logger.debug(f"Removing common condition: '{cond}' (matches MV condition: '{mv_conds[i]}')")
                    break
            
            if not is_common:
                unique_conds.append(cond)
                logger.debug(f"Keeping unique condition: '{cond}'")
        
        # Rejoin the conditions
        return ' AND '.join(unique_conds) if unique_conds else ''
    
    def _normalize_condition_for_comparison(self, condition: str, table_mappings: dict[str, str]) -> str:
        """Normalize a condition into a comparable form
        
        Args:
            condition: Original condition
            table_mappings: Table name -> alias mapping
            
        Returns:
            The normalized condition
        """
        # Remove PostgreSQL cast notation (::text, ::integer, etc.)
        normalized = re.sub(r'::\w+(\[\])?', '', condition)
        
        # Remove table aliases (the aliases in table_mappings, and also MV prefixes)
        for table_name, alias in table_mappings.items():
            # Remove alias.
            pattern = r'\b' + re.escape(alias) + r'\.'
            normalized = re.sub(pattern, '', normalized)
        
        # Also remove MV prefixes (mv_leaf_XX., mv_non_leaf_XX.)
        normalized = re.sub(r'\bmv_\w+\.', '', normalized)

        # Remove double quotes around identifiers
        normalized = normalized.replace('"', '')
        
        # Remove parentheses around column names, e.g. (info) → info
        normalized = re.sub(r'\((\w+)\)', r'\1', normalized)
        
        # Convert PostgreSQL operators to standard SQL operators
        # ~~ → LIKE
        normalized = re.sub(r'\s+~~\s+', ' like ', normalized)
        # !~~ → NOT LIKE
        normalized = re.sub(r'\s+!~~\s+', ' not like ', normalized)
        
        # Convert the PostgreSQL array ANY syntax to IN syntax
        # = ANY ('{val1,val2,val3}') → IN (val1,val2,val3)
        any_pattern = r'=\s*any\s*\(\s*\'\{([^}]+)\}\'\s*\)'
        def convert_any_to_in(match):
            values = match.group(1)
            # Split on commas into individual values
            return f'in ({values})'
        normalized = re.sub(any_pattern, convert_any_to_in, normalized, flags=re.IGNORECASE)
        
        # Remove quotes (for comparing values)
        normalized = re.sub(r"'", '', normalized)
        
        # Remove extra outer parentheses
        while normalized.startswith('(') and normalized.endswith(')'):
            normalized = normalized[1:-1].strip()
        
        # Normalize whitespace (including around the equals sign)
        normalized = re.sub(r'\s*=\s*', '=', normalized)  # remove spaces around =
        normalized = re.sub(r'\s*>\s*', '>', normalized)  # remove spaces around >
        normalized = re.sub(r'\s*<\s*', '<', normalized)  # remove spaces around <
        normalized = re.sub(r'\s*,\s*', ',', normalized)  # remove spaces around ,
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        # Convert to lowercase (ignore case)
        normalized = normalized.lower()
        
        return normalized
    
    def _is_join_condition(self, condition: str) -> bool:
        """Determine whether a condition is a join condition
        
        Join conditions have the form alias1.col1 = alias2.col2
        
        Args:
            condition: Condition string
            
        Returns:
            True for a join condition
        """
        # Check the pattern alias1.col1 = alias2.col2
        pattern = r'^\s*(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)\s*$'
        return re.match(pattern, condition.strip()) is not None
    
    def _extract_tables_from_condition(self, condition: str, table_mappings: dict[str, str]) -> list[str]:
        """Extract the table aliases contained in a condition
        
        Args:
            condition: Condition string (e.g. "t.id = ci.movie_id")
            table_mappings: Table name -> alias mapping
            
        Returns:
            List of table aliases
        """
        tables = []
        # Search for the alias.column pattern
        pattern = r'"?([A-Za-z_][A-Za-z0-9_]*)"?\."?([A-Za-z_][A-Za-z0-9_]*)"?'
        matches = re.findall(pattern, condition)
        
        for alias, column in matches:
            # Whether the alias is among the values of table_mappings, or is an MV table name
            if alias in table_mappings.values() or alias.startswith(('leaf_', 'non_leaf_')):
                tables.append(alias)
        
        return list(set(tables))  # remove duplicates
    
    def _remove_redundant_join_conditions(self, where_clause: str, mv_id: str) -> str:
        """Remove redundant join conditions
        
        Example: non_leaf_475.movie_id = mc.movie_id and non_leaf_475.t_id = mc.movie_id
        are equivalent by the definition of the MV, so only one of them is kept
        
        Args:
            where_clause: WHERE clause
            mv_id: ID of the MV
            
        Returns:
            The cleaned-up WHERE clause
        """
        conditions = self._extract_conditions(where_clause)
        
        # Group the join conditions between the same MV and an external table
        join_groups = {}  # {(mv_id, external_table): [conditions]}
        other_conditions = []
        
        for cond in conditions:
            # Check for the form mv_id.col = table.col
            pattern = rf'{re.escape(mv_id)}\.(\w+)\s*=\s*(\w+)\.(\w+)'
            match = re.match(pattern, cond.strip())
            if match:
                mv_col, ext_table, ext_col = match.groups()
                key = (mv_id, ext_table, ext_col)
                if key not in join_groups:
                    join_groups[key] = []
                join_groups[key].append(cond)
            else:
                # Also check the reverse pattern table.col = mv_id.col
                pattern_rev = rf'(\w+)\.(\w+)\s*=\s*{re.escape(mv_id)}\.(\w+)'
                match_rev = re.match(pattern_rev, cond.strip())
                if match_rev:
                    ext_table, ext_col, mv_col = match_rev.groups()
                    key = (mv_id, ext_table, ext_col)
                    if key not in join_groups:
                        join_groups[key] = []
                    join_groups[key].append(cond)
                else:
                    other_conditions.append(cond)
        
        # Select only one condition from each group
        selected_joins = []
        for key, conds in join_groups.items():
            if len(conds) > 1:
                logger.debug(f"Removing redundant join conditions for {key}: {conds}")
                logger.debug(f"  Keeping: {conds[0]}")
            selected_joins.append(conds[0])
        
        # Reconstruct
        all_conditions = selected_joins + other_conditions
        return ' AND '.join(all_conditions) if all_conditions else ''
    
    def _extract_conditions(self, where_clause: str) -> list[str]:
        """Extract individual conditions from the WHERE clause
        
        To handle the BETWEEN...AND syntax correctly, conditions containing BETWEEN are
        temporarily replaced with placeholders before splitting on AND.
        
        Args:
            where_clause: WHERE clause string
            
        Returns:
            List of conditions
        """
        if not where_clause:
            return []
        
        # Temporarily replace BETWEEN...AND clauses with placeholders to protect them
        between_pattern = re.compile(
            r'(\w+\.?\w*\s+BETWEEN\s+[\w\d\'\"\-]+\s+AND\s+[\w\d\'\"\-]+)',
            re.IGNORECASE
        )
        
        between_clauses = {}
        placeholder_counter = 0
        
        def replace_between(match):
            nonlocal placeholder_counter
            placeholder = f'__BETWEEN_PLACEHOLDER_{placeholder_counter}__'
            between_clauses[placeholder] = match.group(1)
            placeholder_counter += 1
            return placeholder
        
        # Replace BETWEEN with placeholders
        protected_clause = between_pattern.sub(replace_between, where_clause)
        
        # Split on AND
        conditions = [c.strip() for c in protected_clause.split(' AND ') if c.strip()]
        
        # Restore the placeholders to the original BETWEEN clauses
        restored_conditions = []
        for cond in conditions:
            restored = cond
            for placeholder, original in between_clauses.items():
                restored = restored.replace(placeholder, original)
            if restored and restored.upper() not in ('WHERE', 'AND', 'OR'):
                restored_conditions.append(restored)
        
        logger.debug(f"Extracted {len(restored_conditions)} conditions from WHERE clause")
        if logger.isEnabledFor(logging.DEBUG):
            for i, cond in enumerate(restored_conditions):
                logger.debug(f"  Condition {i+1}: {cond}")
        
        return restored_conditions
    
    def _update_alias_references(self, clause: str, old_alias: str, view_id: str) -> str:
        """Update alias references in a clause
        
        Args:
            clause: SQL clause (SELECT, WHERE, GROUP BY, etc.)
            old_alias: Original alias
            view_id: New view ID
            
        Returns:
            The updated clause
        """
        # Replace old_alias.column with view_id.old_alias_column
        # Pattern: old_alias. following a word boundary
        pattern = r'\b' + re.escape(old_alias) + r'\.'
        replacement = view_id + '.' + old_alias + '_'
        
        return re.sub(pattern, replacement, clause)
    
    def _reconstruct_sql(self, parts: dict) -> str:
        """Reconstruct a complete SQL statement from the SQL components
        
        Args:
            parts: {'select': str, 'from': str, 'where': str, 'group_by': str}
            
        Returns:
            The complete SQL statement
        """
        sql = f"SELECT {parts['select']}\nFROM {parts['from']}"
        
        if parts['where']:
            sql += f"\nWHERE {parts['where']}"
        
        if parts['group_by']:
            sql += f"\nGROUP BY {parts['group_by']}"
        
        sql += ";"
        
        return sql

    def rewrite_workload(
        self,
        mv_selections: dict[int, list[str]],
        output_dir: str,
        original_queries: dict[int, str] = None,
    ) -> list[str]:
        """Rewrite the entire workload

        Args:
            mv_selections: {query_id: [MV node IDs]}
            output_dir: Output directory
            original_queries: {query_id: original SQL} (optional)

        Returns:
            List of paths of the rewritten query files
        """
        os.makedirs(output_dir, exist_ok=True)
        rewritten_files = []

        for query_id, mv_nodes in mv_selections.items():
            if not mv_nodes or mv_nodes[0] == "NONE":
                continue

            # Get the original query
            if original_queries and query_id in original_queries:
                original_sql = original_queries[query_id]
            elif self.qm and hasattr(self.qm, "query_map") and query_id in self.qm.query_map:
                original_sql = self.qm.query_map[query_id].get("original_sql", "")
            else:
                print(f"Warning: No original SQL for query {query_id}")
                continue

            # Rewrite the query
            rewritten_sql = self._rewrite_query(query_id, mv_nodes, original_sql)

            # Save to a file
            filename = f"query_{query_id}.sql"
            filepath = os.path.join(output_dir, filename)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(rewritten_sql)

            rewritten_files.append(filepath)
            print(f"Rewritten query {query_id}: {filepath}")

        return rewritten_files

    def _rewrite_query(self, query_id: int, mv_nodes: list[str], original_sql: str) -> str:
        """Rewrite a query

        Args:
            query_id: Query ID
            mv_nodes: List of MV node IDs to use
            original_sql: Original SQL

        Returns:
            The rewritten SQL
        """
        if not mv_nodes or not original_sql:
            return original_sql

        # Parse the FROM clause
        from_clause = self.sql_parser.extract_from_clause(original_sql)
        where_clause = self.sql_parser.extract_where_clause(original_sql)

        # Get the table list
        tables = self.sql_parser.extract_tables(from_clause)

        # Replace leaf nodes with MVs
        new_from_parts = []
        replaced_tables = set()

        for table, alias in tables:
            replaced = False

            # Check whether there is an MV corresponding to this table
            if self.qm and hasattr(self.qm, "leaf_nodes_map_r"):
                for mv_node in mv_nodes:
                    if mv_node.startswith("leaf_") and mv_node in self.qm.leaf_nodes_map_r:
                        # leaf_nodes_map_r: {node_id: (operator, table_name, alias, conditions)}
                        operator, table_name, node_alias, conditions = self.qm.leaf_nodes_map_r[mv_node]
                        if table_name == table:
                            new_from_parts.append(f"{mv_node} AS {alias}")
                            replaced_tables.add(table)
                            replaced = True
                            print(f"  Replaced {table} with {mv_node}")
                            break

            if not replaced:
                new_from_parts.append(f"{table} {alias}")

        # New FROM clause
        new_from = ", ".join(new_from_parts)

        # Extract the SELECT clause as is
        select_match = re.search(r"SELECT\s+(.+?)\s+FROM", original_sql, re.IGNORECASE | re.DOTALL)
        select_clause = select_match.group(1) if select_match else "*"

        # Reconstruct the SQL
        rewritten_sql = self.sql_parser.reconstruct_query(
            select_clause=select_clause, from_clause=new_from, where_clause=where_clause
        )

        return rewritten_sql

    def generate_mv_creation_scripts(self, mv_nodes: list[str], output_dir: Path) -> list[str]:
        """Generate MV creation scripts

        Args:
            mv_nodes: List of MV node IDs
            output_dir: Output directory

        Returns:
            List of generated file paths
        """
        if not self.qm:
            print("Warning: No QueryManager available")
            return []

        return self.mv_generator.generate_mv_scripts(mv_nodes, self.qm, str(output_dir))


def load_mv_selections(mv_list_file: str) -> dict[int, list[str]]:
    """Load MV selection results from a CSV file

    Args:
        mv_list_file: Path of mv_y_list.csv

    Returns:
        {query_num: [MV node IDs]}
    """
    import csv

    mv_selections = {}

    if not os.path.exists(mv_list_file):
        return mv_selections

    with open(mv_list_file, encoding="utf-8") as f:
        reader = csv.reader(f)
        for i, row in enumerate(reader):
            if row:
                mv_selections[i] = [node.strip() for node in row if node.strip()]
            else:
                mv_selections[i] = ["NONE"]

    return mv_selections
