"""Graph representation and minimization of join conditions

This module models the join conditions of a SQL query as an undirected graph
and builds a minimum spanning tree to remove
transitively redundant join conditions.

Example:
    Original join conditions:
        t.id = mk.movie_id
        mk.movie_id = at.movie_id
        t.id = at.movie_id  ← redundant (reachable via t→mk→at by transitivity)
    
    After minimization:
        t.id = mk.movie_id
        mk.movie_id = at.movie_id
"""

import re
import logging
from typing import Set, List, Tuple, Dict, Optional

logger = logging.getLogger(__name__)


IDENT = r'"?[A-Za-z_][A-Za-z0-9_]*"?'


class JoinGraph:
    """Represent join conditions as a graph and build a minimum spanning tree
    
    Join conditions are modeled as an undirected graph:
    - Nodes: aliases of tables/MVs
    - Edges: join conditions (alias1.col = alias2.col)
    
    Kruskal's algorithm is used to build a minimum spanning tree
    and remove transitively redundant join conditions.
    
    Attributes:
        nodes: All nodes in the graph (table aliases)
        edges: All edges in the graph (join conditions)
    """
    
    def __init__(self):
        """Initialize"""
        self.nodes: Set[str] = set()
        self.edges: List[Tuple[str, str, str]] = []  # (table1, table2, condition)
        self._parent: Dict[str, str] = {}  # for Union-Find
    
    def add_join_condition(self, table1: str, table2: str, condition: str):
        """Add a join condition to the graph
        
        Args:
            table1: First table alias
            table2: Second table alias
            condition: Join condition (e.g. "t.id = mk.movie_id")
        """
        if table1 and table2 and table1 != table2:
            self.nodes.add(table1)
            self.nodes.add(table2)
            self.edges.append((table1, table2, condition))
            logger.debug(f"Added join edge: {table1} <-> {table2}: {condition}")
    
    def build_minimal_spanning_tree(self) -> List[str]:
        """Build a minimum spanning tree and return the minimal set of join conditions
        
        Uses Kruskal's algorithm:
        1. Initialize every node as a separate set
        2. Try each edge (join condition) in order
        3. Add an edge only if it joins two different sets
        4. Do not add it if it creates a cycle (redundant join)
        
        Returns:
            List of the minimal join conditions
        """
        if not self.nodes:
            logger.debug("No nodes in join graph")
            return []
        
        if len(self.nodes) == 1:
            logger.debug("Only one node in join graph, no joins needed")
            return []
        
        # Initialize Union-Find (each node is its own set)
        self._parent = {node: node for node in self.nodes}
        
        minimal_conditions = []
        redundant_count = 0
        
        logger.info(f"Building minimal spanning tree from {len(self.edges)} join conditions")
        logger.debug(f"Nodes in graph: {sorted(self.nodes)}")
        
        # Try every edge
        for table1, table2, condition in self.edges:
            # Add the join only if it creates a new connection
            if self._union(table1, table2):
                minimal_conditions.append(condition)
                logger.debug(f"  ✓ Keeping join: {condition}")
            else:
                redundant_count += 1
                logger.debug(f"  ✗ Redundant join (creates cycle): {condition}")
        
        logger.info(f"Join minimization: {len(self.edges)} → {len(minimal_conditions)} "
                   f"(removed {redundant_count} redundant joins)")
        
        # Check whether all nodes are connected
        expected_edges = len(self.nodes) - 1
        if len(minimal_conditions) < expected_edges:
            logger.warning(f"Join graph may not be fully connected: "
                          f"{len(self.nodes)} nodes need {expected_edges} joins, "
                          f"but only {len(minimal_conditions)} joins were added")
        elif len(minimal_conditions) == expected_edges:
            logger.info(f"✓ Join graph is fully connected with minimal joins")
        
        return minimal_conditions
    
    def _find(self, x: str) -> str:
        """Union-Find: find the root (with path compression)
        
        Path compression speeds up subsequent lookups.
        
        Args:
            x: Node
            
        Returns:
            Root node
        """
        if self._parent[x] != x:
            # Path compression: attach intermediate nodes directly to the root
            self._parent[x] = self._find(self._parent[x])
        return self._parent[x]
    
    def _union(self, x: str, y: str) -> bool:
        """Union-Find: merge two nodes
        
        Args:
            x: First node
            y: Second node
            
        Returns:
            True if a new merge was made, False if they are already in the same connected component
        """
        px = self._find(x)
        py = self._find(y)
        
        if px != py:
            # They belong to different sets -> merge
            self._parent[px] = py
            return True
        else:
            # They already belong to the same set -> merging would create a cycle, so do not merge
            return False
    
    def get_connectivity_info(self) -> Dict[str, List[str]]:
        """Get connected component information (for debugging)
        
        Returns:
            Dict of {root node: [nodes in that group]}
        """
        components: Dict[str, List[str]] = {}
        
        for node in self.nodes:
            root = self._find(node)
            if root not in components:
                components[root] = []
            components[root].append(node)
        
        return components
    
    @staticmethod
    def parse_join_condition(condition: str) -> Tuple[str, str]:
        """Extract table aliases from a join condition
        
        Join conditions are expected to have one of the following forms:
        - alias1.column1 = alias2.column2
        - alias1.column1=alias2.column2
        
        Args:
            condition: Join condition (e.g. "t.id = mk.movie_id")
            
        Returns:
            Tuple (table1, table2), or ('', '') if parsing fails
        """
        # Normalize: strip leading/trailing whitespace
        condition = condition.strip()
        
        # Pattern alias1.col = alias2.col (supports double-quoted identifiers)
        pattern = rf'({IDENT})\.({IDENT})\s*=\s*({IDENT})\.({IDENT})'
        match = re.search(pattern, condition)
        
        if match:
            table1 = match.group(1).strip('"')
            table2 = match.group(3).strip('"')
            logger.debug(f"Parsed join condition '{condition}' -> ({table1}, {table2})")
            return table1, table2
        
        logger.debug(f"Failed to parse join condition: {condition}")
        return '', ''
    
    @staticmethod
    def is_join_condition(condition: str) -> bool:
        """Determine whether a condition is a join condition
        
        Join conditions have the form alias1.col1 = alias2.col2
        Filter conditions are e.g. alias1.col1 = 'value' or alias1.col1 > 100
        
        Args:
            condition: Condition string
            
        Returns:
            True for a join condition, False for a filter condition
        """
        # Check the pattern alias1.col1 = alias2.col2 (supports double-quoted identifiers)
        pattern = rf'^\s*{IDENT}\.{IDENT}\s*=\s*{IDENT}\.{IDENT}\s*$'
        return re.match(pattern, condition.strip()) is not None


class JoinMinimizer:
    """High-level class that manages join condition minimization
    
    Uses JoinGraph to minimize the join conditions of a SQL WHERE clause.
    """
    
    def __init__(self):
        """Initialize"""
        pass
    
    def minimize_joins(
        self, 
        join_conditions: List[str], 
        filter_conditions: List[str]
    ) -> Tuple[List[str], List[str]]:
        """Minimize join conditions
        
        Args:
            join_conditions: List of join conditions (alias1.col = alias2.col)
            filter_conditions: List of filter conditions (e.g. alias.col = 'value')
            
        Returns:
            (list of minimized join conditions, list of filter conditions)
        """
        if not join_conditions:
            logger.debug("No join conditions to minimize")
            return [], filter_conditions
        
        # Build the join graph
        graph = JoinGraph()
        
        for condition in join_conditions:
            table1, table2 = JoinGraph.parse_join_condition(condition)
            if table1 and table2:
                graph.add_join_condition(table1, table2, condition)
            else:
                logger.warning(f"Could not parse join condition, treating as filter: {condition}")
                filter_conditions.append(condition)
        
        # Build the minimum spanning tree
        minimal_joins = graph.build_minimal_spanning_tree()
        
        # Check connectivity (debug)
        if logger.isEnabledFor(logging.DEBUG):
            components = graph.get_connectivity_info()
            logger.debug(f"Connectivity components: {len(components)}")
            for root, nodes in components.items():
                logger.debug(f"  Component rooted at {root}: {nodes}")
        
        return minimal_joins, filter_conditions
    
    @staticmethod
    def classify_conditions(where_clause: str) -> Tuple[List[str], List[str]]:
        """Classify the WHERE clause into join conditions and filter conditions
        
        Args:
            where_clause: WHERE clause string
            
        Returns:
            (list of join conditions, list of filter conditions)
        """
        if not where_clause:
            return [], []
        
        # Split on AND (protecting BETWEEN...AND)
        conditions = JoinMinimizer._extract_conditions(where_clause)
        
        join_conditions = []
        filter_conditions = []
        
        for cond in conditions:
            if JoinGraph.is_join_condition(cond):
                join_conditions.append(cond)
            else:
                filter_conditions.append(cond)
        
        logger.debug(f"Classified {len(conditions)} conditions: "
                    f"{len(join_conditions)} joins, {len(filter_conditions)} filters")
        
        return join_conditions, filter_conditions
    
    @staticmethod
    def _extract_conditions(where_clause: str) -> List[str]:
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
        
        return restored_conditions
