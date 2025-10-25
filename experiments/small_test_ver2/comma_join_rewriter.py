"""Query rewriting engine with comma JOIN support.

This module extends the advanced rewriting functionality to support
both explicit JOIN syntax and comma-separated (implicit) JOINs.
"""

import re
import logging
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TableInfo:
    """Information about a table in the query."""
    table_name: str
    alias: str
    filters: list[str]


@dataclass
class JoinInfo:
    """Information about a JOIN between two tables."""
    left_alias: str
    right_alias: str
    condition: str
    join_type: str  # INNER, LEFT, RIGHT, FULL


class CommaJoinRewriter:
    """Query rewriting engine that supports comma JOINs.
    
    Features:
    - Parse explicit JOIN syntax (INNER JOIN ... ON)
    - Parse comma-separated tables (FROM t1, t2, t3)
    - Extract JOIN conditions from WHERE clause for comma JOINs
    - Separate JOIN conditions from filter conditions
    - Rewrite queries using Materialized Views
    """
    
    def __init__(self, query_manager, schema_provider):
        """Initialize the rewriter.
        
        Args:
            query_manager: QueryManager instance with node information
            schema_provider: SchemaProvider for table/column information
        """
        self.qm = query_manager
        self.schema_provider = schema_provider
        logger.info("CommaJoinRewriter initialized")
    
    def parse_query(self, sql: str) -> dict:
        """Parse SQL query into structured components.
        
        Args:
            sql: SQL query string
            
        Returns:
            Dictionary with parsed query components:
            {
                'select_clause': str,
                'tables': list[TableInfo],
                'joins': list[JoinInfo],
                'filters': list[str],
                'group_by': str,
                'order_by': str
            }
        """
        try:
            # Extract main clauses
            select_clause = self._extract_select_clause(sql)
            from_clause = self._extract_from_clause(sql)
            where_clause = self._extract_where_clause(sql)
            group_by = self._extract_group_by_clause(sql)
            order_by = self._extract_order_by_clause(sql)
            
            # Parse tables
            tables = self._parse_tables(from_clause)
            
            # Parse JOINs (explicit or comma-based)
            joins = self._parse_joins(from_clause, where_clause, tables)
            
            # Extract remaining filters (non-JOIN conditions)
            filters = self._extract_filters(where_clause, joins)
            
            return {
                'select_clause': select_clause,
                'tables': tables,
                'joins': joins,
                'filters': filters,
                'group_by': group_by,
                'order_by': order_by
            }
        except Exception as e:
            logger.error(f"Error parsing query: {e}")
            return None
    
    def _extract_select_clause(self, sql: str) -> str:
        """Extract SELECT clause from SQL."""
        match = re.search(r'SELECT\s+(.*?)\s+FROM', sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_from_clause(self, sql: str) -> str:
        """Extract FROM clause from SQL."""
        match = re.search(r'FROM\s+(.*?)(?:\s+WHERE|\s+GROUP\s+BY|\s+ORDER\s+BY|;|$)', 
                         sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_where_clause(self, sql: str) -> str:
        """Extract WHERE clause from SQL."""
        match = re.search(r'WHERE\s+(.*?)(?:\s+GROUP\s+BY|\s+ORDER\s+BY|;|$)', 
                         sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_group_by_clause(self, sql: str) -> str:
        """Extract GROUP BY clause from SQL."""
        match = re.search(r'GROUP\s+BY\s+(.*?)(?:\s+ORDER\s+BY|;|$)', 
                         sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_order_by_clause(self, sql: str) -> str:
        """Extract ORDER BY clause from SQL."""
        match = re.search(r'ORDER\s+BY\s+(.*?)(?:;|$)', 
                         sql, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _parse_tables(self, from_clause: str) -> list[TableInfo]:
        """Parse tables from FROM clause.
        
        Supports both:
        - Explicit JOINs: FROM t1 JOIN t2 ON ...
        - Comma JOINs: FROM t1, t2, t3
        
        Args:
            from_clause: FROM clause text
            
        Returns:
            List of TableInfo objects
        """
        tables = []
        
        # Remove JOIN keywords to get base tables
        # Pattern: table_name [AS] alias
        base_clause = re.sub(r'\s+(?:INNER|LEFT|RIGHT|FULL)\s+JOIN\s+', ', ', 
                            from_clause, flags=re.IGNORECASE)
        base_clause = re.sub(r'\s+ON\s+[^,]+', '', base_clause, flags=re.IGNORECASE)
        
        # Extract tables: table_name [AS] alias
        table_pattern = r'(\w+)\s+(?:AS\s+)?(\w+)'
        matches = re.finditer(table_pattern, base_clause, re.IGNORECASE)
        
        for match in matches:
            table_name = match.group(1)
            alias = match.group(2)
            
            # Skip if this is actually a JOIN keyword
            if table_name.upper() in ['JOIN', 'ON', 'WHERE', 'GROUP', 'ORDER']:
                continue
            
            tables.append(TableInfo(
                table_name=table_name,
                alias=alias,
                filters=[]
            ))
        
        logger.debug(f"Parsed tables: {[f'{t.table_name} AS {t.alias}' for t in tables]}")
        return tables
    
    def _parse_joins(self, from_clause: str, where_clause: str, 
                     tables: list[TableInfo]) -> list[JoinInfo]:
        """Parse JOIN information from FROM and WHERE clauses.
        
        Handles:
        1. Explicit JOINs: INNER JOIN t2 ON t1.id = t2.id
        2. Comma JOINs: FROM t1, t2 WHERE t1.id = t2.id
        
        Args:
            from_clause: FROM clause text
            where_clause: WHERE clause text
            tables: List of TableInfo objects
            
        Returns:
            List of JoinInfo objects
        """
        joins = []
        
        # Check for explicit JOINs first
        explicit_joins = self._parse_explicit_joins(from_clause)
        
        if explicit_joins:
            joins.extend(explicit_joins)
            logger.debug(f"Found {len(explicit_joins)} explicit JOINs")
        else:
            # No explicit JOINs, check for comma JOINs
            if len(tables) > 1 and ',' in from_clause:
                # Comma JOIN detected
                comma_joins = self._parse_comma_joins(where_clause, tables)
                joins.extend(comma_joins)
                logger.debug(f"Found {len(comma_joins)} comma JOINs")
        
        return joins
    
    def _parse_explicit_joins(self, from_clause: str) -> list[JoinInfo]:
        """Parse explicit JOIN syntax.
        
        Pattern: [INNER|LEFT|RIGHT|FULL] JOIN table alias ON condition
        
        Args:
            from_clause: FROM clause text
            
        Returns:
            List of JoinInfo objects
        """
        joins = []
        
        # Pattern for JOIN ... ON ...
        join_pattern = r'(INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+)?JOIN\s+(\w+)\s+(?:AS\s+)?(\w+)\s+ON\s+([^,]+?)(?=\s+(?:INNER\s+|LEFT\s+|RIGHT\s+|FULL\s+)?JOIN|WHERE|GROUP|ORDER|;|$)'
        
        matches = re.finditer(join_pattern, from_clause, re.IGNORECASE | re.DOTALL)
        
        for match in matches:
            join_type = (match.group(1) or 'INNER').strip().upper()
            # table_name = match.group(2)
            right_alias = match.group(3)
            condition = match.group(4).strip()
            
            # Extract left alias from condition
            # Pattern: left_alias.col = right_alias.col
            cond_match = re.search(r'(\w+)\.\w+\s*=\s*(\w+)\.\w+', condition)
            if cond_match:
                left_alias = cond_match.group(1)
                
                joins.append(JoinInfo(
                    left_alias=left_alias,
                    right_alias=right_alias,
                    condition=condition,
                    join_type=join_type
                ))
        
        return joins
    
    def _parse_comma_joins(self, where_clause: str, 
                          tables: list[TableInfo]) -> list[JoinInfo]:
        """Parse comma JOINs by extracting JOIN conditions from WHERE clause.
        
        For comma JOINs, the JOIN conditions are in the WHERE clause:
        FROM t1, t2, t3
        WHERE t1.id = t2.id AND t2.id = t3.id AND ...
        
        Args:
            where_clause: WHERE clause text
            tables: List of TableInfo objects
            
        Returns:
            List of JoinInfo objects
        """
        joins = []
        
        if not where_clause or len(tables) < 2:
            return joins
        
        aliases = {t.alias for t in tables}
        
        # Pattern: alias1.col = alias2.col (or alias2.col = alias1.col)
        join_pattern = r'(\w+)\.(\w+)\s*=\s*(\w+)\.(\w+)'
        matches = re.finditer(join_pattern, where_clause)
        
        for match in matches:
            left_alias = match.group(1)
            left_col = match.group(2)
            right_alias = match.group(3)
            right_col = match.group(4)
            
            # Both aliases must be in the table list (not constants or subqueries)
            if left_alias in aliases and right_alias in aliases:
                condition = f"{left_alias}.{left_col} = {right_alias}.{right_col}"
                
                joins.append(JoinInfo(
                    left_alias=left_alias,
                    right_alias=right_alias,
                    condition=condition,
                    join_type='INNER'  # Comma JOINs are always INNER JOINs
                ))
        
        return joins
    
    def _extract_filters(self, where_clause: str, joins: list[JoinInfo]) -> list[str]:
        """Extract filter conditions from WHERE clause.
        
        Separates JOIN conditions from filter conditions.
        
        Args:
            where_clause: WHERE clause text
            joins: List of JoinInfo objects
            
        Returns:
            List of filter condition strings
        """
        if not where_clause:
            return []
        
        # Build set of JOIN conditions to exclude
        join_conditions = {join.condition for join in joins}
        
        # Split WHERE clause by AND
        conditions = re.split(r'\s+AND\s+', where_clause, flags=re.IGNORECASE)
        
        # Filter out JOIN conditions
        filters = []
        for cond in conditions:
            cond = cond.strip()
            # Check if this is a JOIN condition
            if cond not in join_conditions:
                # Check if it matches JOIN pattern
                if not re.match(r'\w+\.\w+\s*=\s*\w+\.\w+', cond):
                    filters.append(cond)
                else:
                    # It's a table.col = table.col pattern but not in our JOIN list
                    # Could be a filter like: t1.status = t2.status (equality filter)
                    # For safety, treat as filter if both sides reference same table
                    match = re.match(r'(\w+)\.\w+\s*=\s*(\w+)\.\w+', cond)
                    if match and match.group(1) == match.group(2):
                        filters.append(cond)
        
        return filters
    
    def rewrite_with_mv(self, sql: str, mv_id: str, mv_covers: set[str]) -> str:
        """Rewrite query using a Materialized View.
        
        Args:
            sql: Original SQL query
            mv_id: MV identifier (e.g., 'leaf_1', 'non_leaf_5')
            mv_covers: Set of table aliases covered by the MV
            
        Returns:
            Rewritten SQL query
        """
        parsed = self.parse_query(sql)
        if not parsed:
            logger.error("Failed to parse query for rewriting")
            return sql
        
        # Check if MV covers all tables (full replacement)
        all_aliases = {t.alias for t in parsed['tables']}
        
        if mv_covers == all_aliases:
            # Full replacement
            return self._rewrite_full_replacement(parsed, mv_id)
        else:
            # Partial replacement
            return self._rewrite_partial_replacement(parsed, mv_id, mv_covers)
    
    def _rewrite_full_replacement(self, parsed: dict, mv_id: str) -> str:
        """Rewrite query with full MV replacement.
        
        Args:
            parsed: Parsed query components
            mv_id: MV identifier
            
        Returns:
            Rewritten SQL
        """
        select_clause = parsed['select_clause']
        
        # Replace all table aliases with MV alias
        for table in parsed['tables']:
            # Replace alias.col → mv_id.col
            select_clause = re.sub(
                rf'\b{table.alias}\.',
                f'{mv_id}.',
                select_clause
            )
        
        # Build rewritten SQL
        rewritten = f"SELECT {select_clause}\nFROM {mv_id}"
        
        # Add GROUP BY if present
        if parsed['group_by']:
            group_by = parsed['group_by']
            for table in parsed['tables']:
                group_by = re.sub(rf'\b{table.alias}\.', f'{mv_id}.', group_by)
            rewritten += f"\nGROUP BY {group_by}"
        
        # Add ORDER BY if present
        if parsed['order_by']:
            order_by = parsed['order_by']
            for table in parsed['tables']:
                order_by = re.sub(rf'\b{table.alias}\.', f'{mv_id}.', order_by)
            rewritten += f"\nORDER BY {order_by}"
        
        rewritten += ";"
        
        logger.info(f"Full replacement with {mv_id}")
        return rewritten
    
    def _rewrite_partial_replacement(self, parsed: dict, mv_id: str, 
                                    mv_covers: set[str]) -> str:
        """Rewrite query with partial MV replacement.
        
        Args:
            parsed: Parsed query components
            mv_id: MV identifier
            mv_covers: Set of table aliases covered by MV
            
        Returns:
            Rewritten SQL
        """
        select_clause = parsed['select_clause']
        
        # Replace covered table aliases with MV alias
        for table in parsed['tables']:
            if table.alias in mv_covers:
                select_clause = re.sub(
                    rf'\b{table.alias}\.',
                    f'{mv_id}.',
                    select_clause
                )
        
        # Build FROM clause
        from_parts = [mv_id]
        
        # Add uncovered tables
        for table in parsed['tables']:
            if table.alias not in mv_covers:
                from_parts.append(f"{table.table_name} AS {table.alias}")
        
        from_clause = ", ".join(from_parts)
        
        # Build WHERE clause (JOINs + filters)
        where_parts = []
        
        # Add JOIN conditions
        for join in parsed['joins']:
            left_in_mv = join.left_alias in mv_covers
            right_in_mv = join.right_alias in mv_covers
            
            if left_in_mv and right_in_mv:
                # Both in MV, skip (already joined)
                continue
            elif left_in_mv or right_in_mv:
                # One in MV, rewrite condition
                condition = join.condition
                for alias in mv_covers:
                    condition = re.sub(rf'\b{alias}\.', f'{mv_id}.', condition)
                where_parts.append(condition)
            else:
                # Neither in MV, keep as-is
                where_parts.append(join.condition)
        
        # Add filter conditions (only for tables NOT in MV)
        for filter_cond in parsed['filters']:
            # Check if this filter refers to any covered table
            filter_refers_to_mv = False
            for alias in mv_covers:
                if re.search(rf'\b{alias}\.', filter_cond):
                    filter_refers_to_mv = True
                    break
            
            # Only add filter if it doesn't refer to MV-covered tables
            if not filter_refers_to_mv:
                where_parts.append(filter_cond)
            else:
                logger.debug(f"Skipping filter (already in MV): {filter_cond}")
        
        # Build rewritten SQL
        rewritten = f"SELECT {select_clause}\nFROM {from_clause}"
        
        if where_parts:
            where_clause = " AND ".join(where_parts)
            rewritten += f"\nWHERE {where_clause}"
        
        if parsed['group_by']:
            rewritten += f"\nGROUP BY {parsed['group_by']}"
        
        if parsed['order_by']:
            rewritten += f"\nORDER BY {parsed['order_by']}"
        
        rewritten += ";"
        
        logger.info(f"Partial replacement with {mv_id}, covers: {mv_covers}")
        return rewritten


def main():
    """Test the CommaJoinRewriter with sample queries."""
    logging.basicConfig(level=logging.DEBUG)
    
    # Sample queries
    queries = [
        # Comma JOIN
        """
        SELECT MIN(p.name) AS product_name,
               MIN(o.order_date) AS order_date
        FROM orders AS o,
             products AS p
        WHERE o.order_date >= CURRENT_DATE - INTERVAL '60 days'
          AND o.product_id = p.product_id;
        """,
        
        # Explicit JOIN
        """
        SELECT MIN(p.name) AS product_name,
               MIN(o.order_date) AS order_date
        FROM orders AS o
        INNER JOIN products AS p ON o.product_id = p.product_id
        WHERE o.order_date >= CURRENT_DATE - INTERVAL '60 days';
        """,
        
        # 3-table comma JOIN
        """
        SELECT MIN(u.name), MIN(p.name), MIN(o.order_date)
        FROM users AS u,
             orders AS o,
             products AS p
        WHERE u.user_id = o.user_id
          AND o.product_id = p.product_id
          AND u.age >= 25;
        """
    ]
    
    # Create rewriter (with dummy objects for testing)
    class DummyQM:
        pass
    
    class DummySchema:
        pass
    
    rewriter = CommaJoinRewriter(DummyQM(), DummySchema())
    
    # Test parsing
    for i, query in enumerate(queries, 1):
        print(f"\n{'='*60}")
        print(f"Query {i}:")
        print(f"{'='*60}")
        print(query.strip())
        
        parsed = rewriter.parse_query(query)
        
        if parsed:
            print(f"\n--- Parsed Components ---")
            print(f"SELECT: {parsed['select_clause']}")
            print(f"\nTables:")
            for t in parsed['tables']:
                print(f"  - {t.table_name} AS {t.alias}")
            
            print(f"\nJOINs:")
            for j in parsed['joins']:
                print(f"  - {j.left_alias} {j.join_type} JOIN {j.right_alias}")
                print(f"    ON {j.condition}")
            
            print(f"\nFilters:")
            for f in parsed['filters']:
                print(f"  - {f}")
            
            if parsed['group_by']:
                print(f"\nGROUP BY: {parsed['group_by']}")
            if parsed['order_by']:
                print(f"\nORDER BY: {parsed['order_by']}")


if __name__ == "__main__":
    main()
