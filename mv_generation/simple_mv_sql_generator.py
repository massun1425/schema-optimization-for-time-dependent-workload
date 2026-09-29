"""MV SQL Generator with existing MV support.

This module provides functionality to generate MV creation SQL
that can reference existing MVs.

Features:
- Uses CommaJoinRewriter to rewrite queries with existing MVs
- Time-independent: uses a single QueryParser instance
"""

from typing import Optional
import re
import logging

from mv_generation.enhanced_mv_generator import EnhancedMVGenerator
from mv_generation.comma_join_rewriter import CommaJoinRewriter


logger = logging.getLogger(__name__)


class SimpleMVSQLGenerator:
    """Generate MV SQL that can reference existing MVs.
    
    This class generates CREATE MATERIALIZED VIEW SQL by rewriting
    the base query to reference existing MVs when beneficial.
    """
    
    def __init__(self, qp, db_config: dict | None = None):
        """Initialize MVSQLGenerator.
        
        Args:
            qp: QueryParser instance (single, time-independent)
            db_config: Database configuration dict for SchemaProvider
        """
        self.qp = qp
        self.db_config = db_config
        # Create the SchemaProvider only once and reuse it (performance optimization)
        from src.rewrite.schema_provider import SchemaProvider
        self.schema_provider = SchemaProvider(self.db_config)
    
    def generate_mv_sql(
        self, 
        node_id: str, 
        existing_mvs: list[str]
    ) -> Optional[str]:
        """Generate MV SQL taking existing MVs into account.
        
        Args:
            node_id: Node ID of the MV to generate
            existing_mvs: List of existing MV node IDs (reusable MVs)
            
        Returns:
            CREATE MATERIALIZED VIEW statement, or None if generation fails
        """
        if not hasattr(self.qp, 'qm'):
            print(f"  Error: QueryParser has no qm")
            return None
        
        try:
            # 1. Generate the original MV definition with EnhancedMVGenerator (using the reused schema_provider)
            mv_generator = EnhancedMVGenerator(
                query_manager=self.qp.qm,
                schema_provider=self.schema_provider,
                selected_mvs=set(),  # generate a plain query without existing MVs
                query_parser=self.qp,  # provides access to the join conditions of the original SQL
            )
            
            original_sql = mv_generator.generate_mv_sql(node_id)
            
            if not original_sql:
                print(f"  Error: MV SQL generation failed for {node_id}")
                return None
            
            print(f"  [INFO] Original SQL generated")
            
            # 2. Remove the CREATE MATERIALIZED VIEW ... AS part to get the base query
            base_query = self._extract_query_from_create(original_sql)
            
            if not base_query:
                print(f"  Error: query extraction failed for {node_id}")
                return None
            
            # 3. If there are existing MVs, rewrite with CommaJoinRewriter
            if existing_mvs:
                print(f"  [INFO] Rewriting using {len(existing_mvs)} existing MV(s)")
                
                # Initialize CommaJoinRewriter (using the reused schema_provider)
                comma_rewriter = CommaJoinRewriter(
                    query_manager=self.qp.qm,
                    schema_provider=self.schema_provider
                )
                
                # Determine the coverage of each existing MV
                mv_dict = {}  # mv_id -> set of covered aliases
                for mv_id in existing_mvs:
                    mv_tables = self._get_mv_covered_aliases(mv_id, base_query)
                    if mv_tables:
                        print(f"  [INFO] {mv_id} covers: {mv_tables}")
                        mv_dict[mv_id] = mv_tables
                    else:
                        print(f"  [INFO] {mv_id} does not cover the query")
                
                # Rewrite with multiple MVs
                if mv_dict:
                    rewritten_query = comma_rewriter.rewrite_with_multiple_mvs(
                        base_query, 
                        mv_dict
                    )
                else:
                    rewritten_query = base_query
            else:
                print(f"  [INFO] No existing MVs, using the base query")
                rewritten_query = base_query
            
            # 4. Convert to a CREATE MATERIALIZED VIEW statement
            create_sql = f"CREATE MATERIALIZED VIEW {node_id} AS\n{rewritten_query};"
            
            print(f"  [INFO] {node_id}: SQL generated")
            if existing_mvs:
                print(f"  [INFO] Reused MVs: {existing_mvs}")
            
            return create_sql
            
        except Exception as e:
            print(f"  Error: SQL generation failed - {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_query_from_create(self, create_sql: str) -> Optional[str]:
        """Extract the SELECT query from a CREATE MATERIALIZED VIEW statement.
        
        Args:
            create_sql: CREATE MATERIALIZED VIEW statement
            
        Returns:
            The SELECT query part, or None if extraction fails
        """
        import re
        match = re.search(r'CREATE MATERIALIZED VIEW\s+\w+\s+AS\s+(.+)', 
                         create_sql, re.DOTALL | re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            # Remove the trailing semicolon
            query = query.rstrip(';').strip()
            return query
        return None
    
    
    def _get_mv_tables_info(self, mv_node_id: str) -> Optional[dict]:
        """Get information on the tables contained in the MV.
        
        Args:
            mv_node_id: Node ID of the MV
            
        Returns:
            {'tables': [table_name, ...], 'aliases': [alias, ...]} or None
        """
        # leaf_node case
        if mv_node_id in self.qp.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = self.qp.qm.leaf_nodes_map_r[mv_node_id]
            return {
                'tables': [table_name],
                'aliases': [alias],
                'filters': [filter_cond] if filter_cond else []
            }
        
        # non_leaf_node case
        elif mv_node_id in self.qp.qm.non_leaf_nodes_info:
            all_tables = self._get_all_tables(mv_node_id)
            if all_tables:
                tables = [t[0] for t in all_tables]
                aliases = [t[1] for t in all_tables]
                return {
                    'tables': tables,
                    'aliases': aliases,
                    'filters': []
                }
        
        return None
    
    def _get_mv_covered_aliases(
        self, 
        mv_id: str, 
        query: str
    ) -> Optional[set]:
        """Get the table aliases covered by the MV.
        
        Args:
            mv_id: Node ID of the MV
            query: Query string
            
        Returns:
            Set of covered aliases, or None
        """
        try:
            # Get the table information of the MV
            mv_info = self._get_mv_tables_info(mv_id)
            if not mv_info:
                return None
            
            mv_aliases = set(mv_info['aliases'])
            
            # Extract the table aliases from the query and check them
            # Use CommaJoinRewriter.parse_query (with the reused schema_provider)
            from mv_generation.comma_join_rewriter import CommaJoinRewriter
            
            rewriter = CommaJoinRewriter(self.qp.qm, self.schema_provider)
            
            # Parse the query to find the tables it uses
            parsed = rewriter.parse_query(query)
            if not parsed:
                return None
            
            query_aliases = set()
            for table_info in parsed['tables']:
                query_aliases.add(table_info.alias)
            
            # Check whether the MV aliases appear in the query
            covered = mv_aliases & query_aliases
            
            return covered if covered else None
            
        except Exception as e:
            print(f"  [WARN] MV coverage check error ({mv_id}): {e}")
            return None
    
    

    def _get_all_tables(self, node_id: str) -> list[tuple[str, str]]:
        """Recursively collect all tables (table_name, alias) under a node ID.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of (table_name, alias) tuples
        """
        tables = []
        if node_id in self.qp.qm.leaf_nodes_map_r:
            operator, table_name, alias, filter_cond = self.qp.qm.leaf_nodes_map_r[node_id]
            tables.append((table_name, alias))
        elif node_id in self.qp.qm.non_leaf_nodes_info:
            info = self.qp.qm.non_leaf_nodes_info[node_id]
            for child in info.children:
                tables.extend(self._get_all_tables(child))
        return tables


