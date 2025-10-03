"""Query manager for handling query nodes and their relationships.

This module provides the QueryManager class which manages the mapping
between query nodes (leaf and non-leaf) and their properties.
"""

from typing import Dict, List, Tuple, Optional, Any


class QueryManager:
    """Manages query nodes and their relationships.
    
    This class maintains mappings between query node properties and their IDs,
    handles node creation with deduplication, and tracks node positions,
    costs, and sizes.
    
    Attributes:
        leaf_nodes_map: Maps (operator, table, alias, filter) to leaf node ID
        leaf_nodes_map_r: Reverse map from leaf node ID to properties tuple
        non_leaf_nodes_map: Maps sorted child IDs tuple to non-leaf node ID
        non_leaf_nodes_map_r: Reverse map from non-leaf node ID to child IDs
        non_leaf_nodes_filter: Maps non-leaf node ID to filter condition
        leaf_id_counter: Counter for generating unique leaf node IDs
        non_leaf_id_counter: Counter for generating unique non-leaf node IDs
        subquery_positions: Maps node ID to list of [query_id, position] pairs
        subquery_costs: Maps node ID to total cost
        subquery_sizes: Maps node ID to size (rows * width)
        relation_tables: Maps leaf node ID to table name
        subquery_widths: Maps node ID to width in bytes
    """
    
    def __init__(self) -> None:
        """Initialize the QueryManager with empty mappings."""
        # Leaf node mappings
        self.leaf_nodes_map: Dict[Tuple[str, str, str, str], str] = {}
        self.leaf_nodes_map_r: Dict[str, Tuple[str, str, str, str]] = {}
        
        # Non-leaf node mappings
        self.non_leaf_nodes_map: Dict[Tuple[str, ...], str] = {}
        self.non_leaf_nodes_map_r: Dict[str, Tuple[str, ...]] = {}
        self.non_leaf_nodes_filter: Dict[str, str] = {}
        
        # ID counters
        self.leaf_id_counter: int = 0
        self.non_leaf_id_counter: int = 0
        
        # Node properties
        self.subquery_positions: Dict[str, List[List[int]]] = {}
        self.subquery_costs: Dict[str, float] = {}
        self.subquery_sizes: Dict[str, int] = {}
        self.relation_tables: Dict[str, str] = {}
        self.subquery_widths: Dict[str, int] = {}
    
    def _generate_unique_id(self, prefix: str) -> str:
        """Generate a unique ID for a query node.
        
        Args:
            prefix: Type of node ('leaf' or 'non_leaf')
            
        Returns:
            Unique node ID string
            
        Raises:
            ValueError: If prefix is not 'leaf' or 'non_leaf'
        """
        if prefix == "leaf":
            self.leaf_id_counter += 1
            return f"leaf_{self.leaf_id_counter}"
        elif prefix == "non_leaf":
            self.non_leaf_id_counter += 1
            return f"non_leaf_{self.non_leaf_id_counter}"
        else:
            raise ValueError(f"Invalid prefix: {prefix}. Must be 'leaf' or 'non_leaf'")
    
    def process_leaf_node(
        self,
        operator_name: str,
        table_name: str,
        alias: str,
        filter_condition: str,
        position: List[int],
        total_cost: float,
        size: int,
        width: int
    ) -> str:
        """Process a leaf node (table scan).
        
        If a leaf node with the same properties already exists, returns its ID.
        Otherwise, creates a new leaf node and returns the new ID.
        
        Args:
            operator_name: Operator type (e.g., 'Seq Scan', 'Index Scan')
            table_name: Name of the table being scanned
            alias: Alias used in the query
            filter_condition: Filter condition applied
            position: [query_id, position] in the query plan
            total_cost: Cost of executing this node
            size: Size of result set (rows * width)
            width: Width of result tuples in bytes
            
        Returns:
            Node ID for this leaf node
        """
        key = (operator_name, table_name, alias, filter_condition)
        
        # Check if this leaf node already exists
        if key in self.leaf_nodes_map:
            node_id = self.leaf_nodes_map[key]
        else:
            # Create new leaf node
            node_id = self._generate_unique_id("leaf")
            self.leaf_nodes_map[key] = node_id
            self.leaf_nodes_map_r[node_id] = key
        
        # Update position if valid
        if position[0] != -1:
            if node_id in self.subquery_positions:
                self.subquery_positions[node_id].append(position)
            else:
                self.subquery_positions[node_id] = [position]
        
        # Update cost (keep minimum cost)
        if node_id in self.subquery_costs:
            if self.subquery_costs[node_id] >= total_cost:
                self.subquery_costs[node_id] = total_cost
        else:
            self.subquery_costs[node_id] = total_cost
        
        # Update other properties
        self.subquery_sizes[node_id] = size
        self.relation_tables[node_id] = table_name
        self.subquery_widths[node_id] = width
        
        return node_id
    
    def process_non_leaf_node(
        self,
        child_node_ids: List[str],
        position: List[int],
        total_cost: float,
        size: int,
        width: int,
        filter_condition: str = ""
    ) -> str:
        """Process a non-leaf node (join, aggregation, etc.).
        
        If a non-leaf node with the same children already exists, returns its ID.
        Otherwise, creates a new non-leaf node and returns the new ID.
        
        Args:
            child_node_ids: List of child node IDs
            position: [query_id, position] in the query plan
            total_cost: Cost of executing this node
            size: Size of result set (rows * width)
            width: Width of result tuples in bytes
            filter_condition: Filter condition applied after operation
            
        Returns:
            Node ID for this non-leaf node
        """
        # Create key from sorted child IDs for deduplication
        key = tuple(sorted(child_node_ids))
        
        # Check if this non-leaf node already exists
        if key in self.non_leaf_nodes_map:
            node_id = self.non_leaf_nodes_map[key]
        else:
            # Create new non-leaf node
            node_id = self._generate_unique_id("non_leaf")
            self.non_leaf_nodes_map[key] = node_id
            self.non_leaf_nodes_map_r[node_id] = key
        
        # Update position if valid
        if position[0] != -1:
            if node_id in self.subquery_positions:
                self.subquery_positions[node_id].append(position)
            else:
                self.subquery_positions[node_id] = [position]
        
        # Update properties
        self.non_leaf_nodes_filter[node_id] = filter_condition
        self.subquery_costs[node_id] = total_cost
        self.subquery_sizes[node_id] = size
        self.subquery_widths[node_id] = width
        
        return node_id
    
    def depth_first_search(self, node: Dict[str, Any], position: List[int]) -> str:
        """Perform depth-first search on a query plan tree.
        
        Recursively processes nodes in the query plan, creating or finding
        corresponding node IDs in the manager.
        
        Args:
            node: Query plan node dictionary with keys:
                - type: 'leaf' or 'non_leaf'
                - operator: Operator type
                - For leaf: table, alias, filter, cost, size, width
                - For non-leaf: children, filter, cost, size, width
            position: [query_id, position] in the query plan
            
        Returns:
            Node ID for the processed node
            
        Raises:
            ValueError: If node type is invalid
        """
        if node["type"] == "leaf":
            return self.process_leaf_node(
                node["operator"],
                node["table"],
                node["alias"],
                node["filter"],
                position,
                node["cost"],
                node["size"],
                node["width"]
            )
        elif node["type"] == "non_leaf":
            # Recursively process children
            child_ids = [
                self.depth_first_search(child, [-1, -1])
                for child in node["children"]
            ]
            return self.process_non_leaf_node(
                child_ids,
                position,
                node["cost"],
                node["size"],
                node["width"],
                node.get("filter", "")
            )
        else:
            raise ValueError(f"Invalid node type: {node.get('type')}")
    
    def depth_child_to_parent_search(
        self,
        node: Dict[str, Any],
        child_to_parent: Dict[str, List[str]],
        parent_id: str
    ) -> Dict[str, List[str]]:
        """Build child-to-parent mapping via depth-first search.
        
        This method is used to construct dependency relationships between nodes.
        
        Args:
            node: Query plan node dictionary
            child_to_parent: Dictionary mapping child node ID to parent IDs
            parent_id: ID of the parent node
            
        Returns:
            Updated child_to_parent dictionary
        """
        if node["type"] == "non_leaf":
            # Recursively process children
            child_ids = [
                self.depth_child_to_parent_search(child, child_to_parent, parent_id)
                for child in node["children"]
            ]
            
            # Create the current node
            current_node = self.process_non_leaf_node(
                child_ids,
                [-1, -1],
                node["cost"],
                node["size"],
                node["width"],
                node.get("filter", "")
            )
            
            # Record parent relationship
            child_to_parent[current_node] = [parent_id]
            
            # Debug output (consider using logging in production)
            print(f"child_ids= {child_ids}")
            print(f"current_node= {current_node}")
            print(f"parent_id= {parent_id}")
        
        return child_to_parent
    
    def get_node_info(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a node.
        
        Args:
            node_id: ID of the node to query
            
        Returns:
            Dictionary with node information or None if not found
        """
        info = {}
        
        # Check if it's a leaf node
        if node_id in self.leaf_nodes_map_r:
            operator, table, alias, filter_cond = self.leaf_nodes_map_r[node_id]
            info = {
                "type": "leaf",
                "node_id": node_id,
                "operator": operator,
                "table": table,
                "alias": alias,
                "filter": filter_cond
            }
        # Check if it's a non-leaf node
        elif node_id in self.non_leaf_nodes_map_r:
            children = self.non_leaf_nodes_map_r[node_id]
            info = {
                "type": "non_leaf",
                "node_id": node_id,
                "children": list(children),
                "filter": self.non_leaf_nodes_filter.get(node_id, "")
            }
        else:
            return None
        
        # Add common properties
        info.update({
            "cost": self.subquery_costs.get(node_id),
            "size": self.subquery_sizes.get(node_id),
            "width": self.subquery_widths.get(node_id),
            "positions": self.subquery_positions.get(node_id, [])
        })
        
        return info
    
    def reset(self) -> None:
        """Reset all mappings and counters.
        
        Useful for processing a new workload from scratch.
        """
        self.leaf_nodes_map.clear()
        self.leaf_nodes_map_r.clear()
        self.non_leaf_nodes_map.clear()
        self.non_leaf_nodes_map_r.clear()
        self.non_leaf_nodes_filter.clear()
        self.leaf_id_counter = 0
        self.non_leaf_id_counter = 0
        self.subquery_positions.clear()
        self.subquery_costs.clear()
        self.subquery_sizes.clear()
        self.relation_tables.clear()
        self.subquery_widths.clear()
