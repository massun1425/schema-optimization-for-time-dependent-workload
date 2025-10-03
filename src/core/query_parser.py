"""Query parser for processing PostgreSQL query plans.

This module provides the QueryParser class which parses JSON query plans
from PostgreSQL EXPLAIN output and processes them for optimization.
"""

import json
import os
import re
import random
from typing import List, Dict, Tuple, Any, Optional

from .query_manager import QueryManager
from ..utils.legacy import get_red_queries, natural_sort_key
from config.settings import Settings


class QueryParser:
    """Parses and processes query plans for materialized view optimization.
    
    This class handles:
    - Loading and parsing JSON query plans from PostgreSQL EXPLAIN
    - Converting query plans into internal representation
    - Computing utility and cost metrics
    - Building dependency relationships between subqueries
    
    Attributes:
        qm: QueryManager instance for managing query nodes
        s_num: Total number of subquery nodes
        m_cost: Maintenance cost for each node
        node_list: List of all node IDs
        position_node_id: Maps (query_id, position) to node_id
        deeplist: List of depth lists for each query
        U_j_max: Maximum utility for each node
        b_j: Storage size for each node
        q_s_list: Binary matrix of query-to-subquery relationships
        q_s_order_list: Execution order of subqueries in each query
        u_ij: Utility matrix [query_id][node_id]
        us_ij: Shared utility matrix
        y_ij: Decision variables (for ILP)
        X: Inclusive dependency matrix
        U_max: Maximum total utility
        query: List of processed query plans
        subqlist: Reverse mapping of non-leaf nodes to children
    """
    
    def __init__(self, settings: Optional[Settings] = None) -> None:
        """Initialize the QueryParser.
        
        Args:
            settings: Configuration settings (optional, loads default if None)
        """
        self.settings = settings or Settings()
        self.qm = QueryManager()
        
        # Initialize result attributes
        self.s_num: int = 0
        self.m_cost: List[float] = []
        self.node_list: List[str] = []
        self.position_node_id: Dict[Tuple[int, int], str] = {}
        self.deeplist: List[List[int]] = []
        self.U_j_max: List[float] = []
        self.b_j: List[int] = []
        self.q_s_list: List[List[int]] = []
        self.q_s_order_list: List[List[int]] = []
        self.u_ij: List[List[float]] = []
        self.us_ij: List[List[float]] = []
        self.y_ij: List[List[int]] = []
        self.X: List[List[int]] = []
        self.U_max: float = 0.0
        self.query: List[List[Dict[str, Any]]] = []
        self.subqlist: Dict[Tuple[str, ...], str] = {}
    
    def natural_sort_key(self, s: str) -> List:
        """Generate a key for natural sorting of strings with numbers.
        
        Args:
            s: String to generate sort key for
            
        Returns:
            List of strings and integers for sorting
        """
        return [int(text) if text.isdigit() else text.lower() 
                for text in re.split('([0-9]+)', s)]
    
    def convert_node(
        self,
        node: Dict[str, Any],
        subquery_list: List[Dict[str, Any]],
        deep_list: List[int],
        order_list: List[int],
        order: int,
        depth: int = 0,
        table_info: List[str] = None,
        frequency: int = 1
    ) -> Tuple[Dict[str, Any], int]:
        """Convert a PostgreSQL plan node to internal representation.
        
        Args:
            node: PostgreSQL EXPLAIN plan node
            subquery_list: Accumulated list of converted subqueries
            deep_list: Accumulated list of node depths
            order_list: Accumulated list of execution orders
            order: Current execution order
            depth: Current depth in the plan tree
            table_info: Table info for Bitmap Heap Scan [table_name, alias]
            frequency: Query execution frequency
            
        Returns:
            Tuple of (converted node dict, next order number)
        """
        if table_info is None:
            table_info = []
            
        deep_list.append(depth)
        
        if "Plans" in node:  # Non-leaf node
            children = []
            new_order = order
            
            # Special handling for Bitmap Heap Scan
            if node["Node Type"] == "Bitmap Heap Scan":
                table_info = [node["Relation Name"], node["Alias"]]
            
            # Recursively process children
            for child in node["Plans"]:
                converted_child, order_1 = self.convert_node(
                    child, subquery_list, deep_list, order_list,
                    new_order + 1, depth + 1, table_info, frequency
                )
                children.append(converted_child)
                new_order = order_1
            
            # Determine filter condition key based on operator type
            if node["Node Type"] == "Hash Join":
                filter_name = "Hash Cond"
            elif node["Node Type"] == "Merge Join":
                filter_name = "Merge Cond"
            elif node["Node Type"] == "Nested Loop":
                filter_name = "Join Filter"
            else:
                filter_name = "Filter"
            
            filter_condition = node.get(filter_name, "")
            
            # Cost calculation logic
            # Prevent MVs with no filter condition
            if "Seq Scan" in node["Node Type"] and filter_condition == "":
                cost = 0.0
            # Edge case: Hash node with no filter in child
            elif (node["Node Type"] == "Hash" and "Plans" in node and 
                  "Filter" not in node["Plans"][0]):
                cost = 0.0
            else:
                cost = node.get("Total Cost", 0.0)
            
            # Zero cost if no filter
            if filter_condition == "":
                cost = 0.0
            
            # Ensure non-zero width
            width = node.get("Plan Width", 0)
            if width == 0:
                width = 1
            
            subquery_list.append({
                "type": "non_leaf",
                "operator": node["Node Type"],
                "filter": filter_condition,
                "cost": cost * frequency,
                "size": node.get("Plan Rows", 0) * width,
                "width": width,
                "children": children
            })
            order_list.append(order)
            return subquery_list[-1], new_order
        
        else:  # Leaf node
            # Determine filter condition
            if "Index Cond" in node and "Filter" in node:
                filter_condition = f"{node['Index Cond']} AND {node['Filter']}"
                cost = node["Total Cost"]
            elif "Index Cond" in node:
                filter_condition = node["Index Cond"]
                cost = node["Total Cost"]
            elif "Filter" in node:
                filter_condition = node["Filter"]
                cost = node["Total Cost"]
            else:
                filter_condition = ""
                cost = 0.0
            
            # Zero cost for scan without filter
            if "Scan" in node["Node Type"] and "Filter" not in node:
                cost = 0.0
            
            # Ensure non-zero width
            width = node.get("Plan Width", 0)
            if width == 0:
                width = 1
            
            # Handle Bitmap Index Scan
            if node["Node Type"] == "Bitmap Index Scan":
                table = table_info[0] if len(table_info) > 0 else ""
                alias = table_info[1] if len(table_info) > 1 else ""
            else:
                table = node.get("Relation Name", "")
                alias = node.get("Alias", "")
            
            subquery_list.append({
                "type": "leaf",
                "operator": node["Node Type"],
                "table": table,
                "alias": alias,
                "filter": filter_condition,
                "cost": cost * frequency,
                "size": node.get("Plan Rows", 0) * width,
                "width": width
            })
            order_list.append(order)
            return subquery_list[-1], order
    
    def convert_json(
        self,
        json_data: List[Dict[str, Any]],
        freq: int
    ) -> Tuple[List[Dict[str, Any]], List[int], List[int]]:
        """Convert JSON query plan data to internal representation.
        
        Args:
            json_data: List of PostgreSQL EXPLAIN output plans
            freq: Query execution frequency
            
        Returns:
            Tuple of (subquery_list, depth_list, order_list)
        """
        subquery_list = []
        deep_list = []
        order_list = []
        order = 0
        
        for plan in json_data:
            self.convert_node(
                plan["Plan"], subquery_list, deep_list,
                order_list, order, frequency=freq
            )
        
        return subquery_list, deep_list, order_list
    
    def make_reverse_dict(
        self,
        d: Dict[str, List[List[int]]]
    ) -> Dict[Tuple[int, int], str]:
        """Create reverse dictionary from position lists.
        
        Args:
            d: Dictionary mapping node_id to list of [query_id, position] pairs
            
        Returns:
            Dictionary mapping (query_id, position) to node_id
        """
        reverse_dict = {}
        for key, value in d.items():
            if len(value) == 1:
                v_tuple = tuple(value[0])
                reverse_dict[v_tuple] = key
            else:
                for v in value:
                    v_tuple = tuple(v)
                    reverse_dict[v_tuple] = key
        return reverse_dict
    
    def make_reverse_dict2(
        self,
        d: Dict[Tuple[str, ...], str]
    ) -> Dict[str, Tuple[str, ...]]:
        """Create reverse dictionary.
        
        Args:
            d: Dictionary mapping children tuple to node_id
            
        Returns:
            Dictionary mapping node_id to children tuple
        """
        reverse_dict = {}
        for key, value in d.items():
            reverse_dict[value] = key
        return reverse_dict
    
    def search_leaf_node(self, node_id: str) -> List[str]:
        """Find all leaf table names in a subtree.
        
        Recursively searches the subtree rooted at node_id and returns
        a list of all table names referenced by leaf nodes.
        
        Args:
            node_id: Root node ID to start search from
            
        Returns:
            List of unique table names
        """
        leaf_tables = set()
        
        def _find_leaf_tables_recursive(current_node_id: str) -> None:
            if current_node_id.startswith("leaf_"):
                table_name = self.qm.relation_tables.get(current_node_id)
                if table_name:
                    leaf_tables.add(table_name)
            elif current_node_id.startswith("non_leaf_"):
                child_node_ids = self.qm.non_leaf_nodes_map_r.get(current_node_id, [])
                for child_id in child_node_ids:
                    _find_leaf_tables_recursive(child_id)
        
        _find_leaf_tables_recursive(node_id)
        return list(leaf_tables)
    
    def check_m_cost(
        self,
        m_cost: List[float],
        table_list: List[str],
        update_table: List[List[str]],
        record_list: List[int],
        search_cost: List[float],
        insert_cost: float,
        table_width: List[int],
        insert_times: float
    ) -> List[float]:
        """Calculate maintenance cost for materialized views.
        
        Args:
            m_cost: Initial maintenance cost list (will be updated)
            table_list: List of table names
            update_table: List of tables being updated
            record_list: Number of records in each table
            search_cost: Search cost for each table
            insert_cost: Cost per insert operation (alpha)
            table_width: Width of each table in bytes
            insert_times: Number of insert operations
            
        Returns:
            Updated maintenance cost list
        """
        len_leaf = len(self.qm.leaf_nodes_map)
        
        # Calculate maintenance cost for leaf nodes
        for i in range(len(self.qm.leaf_nodes_map)):
            node_id = f"leaf_{i + 1}"
            for item in update_table:
                item2 = self.qm.relation_tables[node_id]
                if item[0] == item2:
                    m_cost[i] += (self.qm.subquery_costs[node_id] / 
                                  record_list[table_list.index(item2)])
                    m_cost[i] += (insert_cost * self.qm.subquery_widths[node_id] / 
                                  table_width[table_list.index(item2)])
            m_cost[i] *= insert_times
        
        # Calculate maintenance cost for non-leaf nodes
        for i in range(len(self.qm.non_leaf_nodes_map)):
            node_id = f"non_leaf_{i + 1}"
            node_id_table_list = self.search_leaf_node(node_id)
            for item in update_table:
                if item[0] in node_id_table_list:
                    m_cost[i + len_leaf] += (self.qm.subquery_costs[node_id] / 
                                             record_list[table_list.index(item[0])])
                    m_cost[i + len_leaf] += (insert_cost * self.qm.subquery_widths[node_id] / 
                                             table_width[table_list.index(item[0])])
            m_cost[i + len_leaf] *= insert_times
        
        return m_cost
    
    def set_inclusive_dependency(
        self,
        X: Optional[List[List[int]]],
        j: int,
        parent: Optional[str] = None
    ) -> List[List[int]]:
        """Build inclusive dependency matrix recursively.
        
        The dependency matrix X indicates which nodes must be materialized
        together (if node i is materialized, all its descendants must be too).
        
        Args:
            X: Dependency matrix (None for initial call)
            j: Current row index
            parent: Parent node ID
            
        Returns:
            Updated dependency matrix
        """
        if parent is None:
            # Initialize matrix
            X = [[0] * len(self.node_list) for _ in range(len(self.node_list))]
            for j in range(len(self.node_list)):
                parent = self.node_list[j]
                if parent in self.subqlist.keys():
                    for child in self.subqlist[parent]:
                        X[j][self.node_list.index(child)] = 1
                        X = self.set_inclusive_dependency(X, j, child)
        else:
            if parent not in self.subqlist.keys():
                return X
            for child in self.subqlist[parent]:
                X[j][self.node_list.index(child)] = 1
                X = self.set_inclusive_dependency(X, j, child)
        
        return X
    
    def query_parse(
        self,
        q_num: int,
        path: str,
        insert_query: int
    ) -> None:
        """Parse workload and compute optimization parameters.
        
        This is the main entry point for parsing a query workload.
        It processes all queries, builds node relationships, and computes
        utility and cost metrics needed for optimization.
        
        Args:
            q_num: Number of queries (currently not used, determined from files)
            path: Path to directory containing JSON query plans
            insert_query: Number of insert queries for maintenance cost
            
        Raises:
            json.JSONDecodeError: If JSON parsing fails
        """
        workloads_dir = self.settings.benchmark.workloads_dir
        get_ceb = self.settings.benchmark.type == "ceb"
        
        # Get query files with frequencies
        files, file_freq = get_red_queries(path, workloads_dir, get_ceb)
        files = sorted(files, key=natural_sort_key)
        
        q_num_len = len(files)
        print(f"q_num_len= {q_num_len}")
        
        try:
            query = []
            deeplist = []
            orderlist = []
            
            # Process each query file
            for i in range(q_num_len):
                with open(files[i], 'r') as f:
                    data = json.load(f)
                    frequency = file_freq[files[i]]
                    converted_data, deep_list, order_list = self.convert_json(data, frequency)
                    deeplist.append(deep_list)
                    orderlist.append(order_list)
                    
                    # Process nodes with DFS
                    for j, subquery in zip(order_list, converted_data):
                        result = self.qm.depth_first_search(subquery, [i, j])
                    
                    query.append(converted_data)
            
            # Build child-to-parent relationships
            child_to_parent = {}
            for key, value in self.qm.non_leaf_nodes_map.items():
                for item in key:
                    if item not in child_to_parent:
                        child_to_parent[item] = []
                    child_to_parent[item].append(value)
            
            print(f"Root node ID: {result}")
            
            # Build node lists and mappings
            node_list = (list(self.qm.leaf_nodes_map.values()) + 
                        list(self.qm.non_leaf_nodes_map.values()))
            position_node_id = self.make_reverse_dict(self.qm.subquery_positions)
            
            len_leaf = len(self.qm.leaf_nodes_map)
            len_non_leaf = len(self.qm.non_leaf_nodes_map)
            s_num = len_leaf + len_non_leaf
            
            # Count node usage
            s_counter = [0] * s_num
            s_counter2 = [0] * s_num
            
            for j in range(s_num):
                s_counter2[j] = len(self.qm.subquery_positions[node_list[j]])
                if len(self.qm.subquery_positions[node_list[j]]) > 1:
                    s_counter[j] = 1
            
            # Build query-to-subquery matrices
            q_s_list = []
            q_s_order_list = []
            u_ij = []
            us_ij = []
            y_ij = []
            
            for i in range(q_num_len):
                q_by_s = [0] * s_num
                q_s_order = []
                u_ij_seed = [0.0] * s_num
                y_ij_seed = [0] * s_num
                us_ij_seed = [0.0] * s_num
                
                for j in range(s_num):
                    for item in self.qm.subquery_positions[node_list[j]]:
                        if item[0] == i:
                            q_s_order.append(item[1])
                            q_by_s[j] = 1
                            u_ij_seed[j] = self.qm.subquery_costs[node_list[j]]
                            us_ij_seed[j] = (self.qm.subquery_costs[node_list[j]] * 
                                            s_counter[j])
                
                q_s_list.append(q_by_s)
                q_s_order_list.append(q_s_order)
                u_ij.append(u_ij_seed)
                us_ij.append(us_ij_seed)
                y_ij.append(y_ij_seed)
            
            # Calculate storage sizes
            b_j = [0] * s_num
            for j, item in enumerate(node_list):
                b_j[j] = self.qm.subquery_sizes[item]
                if b_j[j] == 0:
                    b_j[j] = 1
            
            # Calculate max budget and utility
            maxb = 0
            maxu = 0.0
            
            for i in range(len(u_ij)):
                p_0 = (i, 0)
                p_1 = (i, 1)
                node_0 = position_node_id[p_0]
                node_1 = position_node_id.get(p_1)
                
                maxb += self.qm.subquery_sizes[node_0]
                
                if len(orderlist[i]) > 1 and node_1:
                    if self.qm.subquery_costs[node_0] < self.qm.subquery_costs[node_1]:
                        maxu += self.qm.subquery_costs[node_1]
                    else:
                        maxu += self.qm.subquery_costs[node_0]
                else:
                    maxu += self.qm.subquery_costs[node_0]
            
            print('total_cost', 'total_budget')
            print(maxu, maxb)
            
            # Calculate max utility per node
            U_max = sum(sum(u_row) for u_row in u_ij)
            U_j_max = [0.0] * s_num
            for i in range(len(u_ij)):
                for j in range(len(u_ij[i])):
                    U_j_max[j] += u_ij[i][j]
            
            # Build dependency matrix
            self.subqlist = self.make_reverse_dict2(self.qm.non_leaf_nodes_map)
            self.node_list = node_list
            X = self.set_inclusive_dependency(None, 0)
            
            # Calculate maintenance costs
            # IMDB schema hardcoded values (should be externalized to config)
            table_list = ['aka_name', 'aka_title', 'cast_info', 'char_name', 
                         'comp_cast_type', 'company_name', 'company_type', 
                         'complete_cast', 'info_type', 'keyword', 'kind_type', 
                         'link_type', 'movie_companies', 'movie_info', 
                         'movie_info_idx', 'movie_keyword', 'movie_link', 'name', 
                         'person_info', 'role_type', 'title']
            record_list = [901343, 361472, 36244344, 3140339, 4, 234997, 4, 
                          135086, 113, 134170, 7, 18, 2609129, 14835720, 
                          1380035, 4523930, 29997, 4167491, 2963664, 12, 2528312]
            insert_cost_alpha = 0.01
            search_cost = [8.44, 8.44, 8.46, 8.45, 8.17, 8.44, 8.17, 8.31, 
                          8.17, 8.44, 8.17, 8.17, 8.45, 8.45, 8.44, 8.45, 
                          8.30, 8.45, 8.45, 8.17, 8.16]
            table_width = [324, 348, 56, 182, 86, 198, 86, 16, 86, 60, 52, 
                          86, 48, 76, 52, 12, 16, 238, 76, 86, 306]
            
            m_cost = [0.0] * (len_leaf + len_non_leaf)
            insert_times = insert_query / 1000
            
            # Generate random update tables
            update_table = [[''] for _ in range(1000)]
            for i in range(len(update_table)):
                x = random.randint(0, 20)
                update_table[i][0] = table_list[x]
            
            m_cost = self.check_m_cost(m_cost, table_list, update_table, 
                                      record_list, search_cost, insert_cost_alpha,
                                      table_width, insert_times)
            
            # Store results as instance attributes
            self.qm = self.qm
            self.s_num = s_num
            self.m_cost = m_cost
            self.node_list = node_list
            self.position_node_id = position_node_id
            self.deeplist = deeplist
            self.U_j_max = U_j_max
            self.b_j = b_j
            self.q_s_list = q_s_list
            self.q_s_order_list = q_s_order_list
            self.u_ij = u_ij
            self.us_ij = us_ij
            self.y_ij = y_ij
            self.X = X
            self.U_max = U_max
            self.query = query
        
        except json.JSONDecodeError as e:
            print(f"Error reading {files[i] if i < len(files) else 'unknown file'}: {e}")
            raise
