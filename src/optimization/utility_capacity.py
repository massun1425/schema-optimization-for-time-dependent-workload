"""Utility-capacity ILP optimization algorithm.

This module implements the utility-capacity ratio based greedy initialization,
selecting MVs based on (utility - maintenance_cost/size).
"""

import time
import copy
from typing import List, Tuple, Optional

from .base import BaseILPOptimizer
from ..core.models import OptimizationResult


class UtilityCapacityOptimizer(BaseILPOptimizer):
    """Utility-capacity ratio based ILP optimizer.
    
    This algorithm uses a greedy initialization based on utility minus
    maintenance cost per unit size: (U - m_cost/size).
    """
    
    def __init__(self, *args, position_node_id=None, deeplist=None, **kwargs):
        """Initialize utility-capacity optimizer.
        
        Args:
            *args: Positional arguments for BaseILPOptimizer
            position_node_id: Mapping from (query_id, position) to node_id
            deeplist: List of depth information for each query
            **kwargs: Keyword arguments for BaseILPOptimizer
        """
        super().__init__(*args, **kwargs)
        self.position_node_id = position_node_id or {}
        self.deeplist = deeplist or []
    
    def initialize_greedy(self) -> List[int]:
        """Initialize solution using utility-capacity greedy heuristic.
        
        Selects MVs in order of (utility - maintenance_cost/size) until
        storage budget is exhausted. This favors smaller MVs with high utility.
        
        Returns:
            Binary list indicating initial MV selection
        """
        mv_list = [0] * self.s_num
        
        # Calculate U_j_max for each node
        U_j_max = copy.deepcopy(self.qm.subquery_costs)
        for node_id in U_j_max:
            U_j_max[node_id] = (U_j_max[node_id] * 
                               len(self.qm.subquery_positions[node_id]))
        
        # Calculate (utility - maintenance_cost/size) for each node
        U_B_list = {}
        for i in range(len(self.node_list)):
            node_id = self.node_list[i]
            size = self.qm.subquery_sizes[node_id]
            if size > 0:
                U_B_list[node_id] = (U_j_max[node_id] - 
                                     self.m_cost[i] / size)
            else:
                U_B_list[node_id] = U_j_max[node_id] - self.m_cost[i]
        
        # Sort by utility-capacity ratio (descending)
        U_B_list_sorted = sorted(U_B_list.items(), key=lambda x: x[1], reverse=True)
        
        # Greedily select MVs until budget exhausted
        b_now = 0
        for node_id, ub_ratio in U_B_list_sorted:
            node_idx = self.node_list.index(node_id)
            if b_now + self.qm.subquery_sizes[node_id] <= self.B_max:
                mv_list[node_idx] = 1
                b_now += self.qm.subquery_sizes[node_id]
        
        return mv_list
    
    def initialize_candidates(self, **kwargs) -> Tuple[List[int], List[int]]:
        """Initialize MV candidates using greedy utility-capacity heuristic.
        
        Returns:
            Tuple of (cand_i, cand_j):
                cand_i: Queries that can benefit from MVs
                cand_j: Subqueries selected by greedy initialization
        """
        # Get greedy initial solution
        z_j = self.initialize_greedy()
        
        # Build M: beneficial subqueries for each query
        M = []
        for i in range(len(self.q_s_list)):
            M_i = []
            M_i_ = []
            for j in range(len(z_j)):
                if self.u_ij[i][j] > 0:
                    M_i.append(j)
                if z_j[j] > 0:
                    M_i_.append(j)
            
            k = list(set(M_i) & set(M_i_))
            M.append(k)
        
        # Candidate queries
        cand_i = []
        for i in range(len(M)):
            if len(M[i]) != 0:
                cand_i.append(i)
        
        # Candidate subqueries
        cand_j = []
        for j in range(len(z_j)):
            if z_j[j] == 1:
                cand_j.append(j)
        
        return cand_i, cand_j
    
    def optimize(self, **kwargs) -> OptimizationResult:
        """Execute the utility-capacity ILP optimization.
        
        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        start_time = time.time()
        
        # Initialize with greedy heuristic
        cand_i, cand_j = self.initialize_candidates()
        
        # Build ILP model
        y, z = self.build_ilp_model(cand_i, cand_j)
        
        # Add constraints
        self.add_common_constraints(y, z, cand_i, cand_j)
        
        # Set objective
        self.set_objective(y, z, cand_i, cand_j)
        
        # Solve
        y_ij, z_j, obj_val = self.solve_ilp(y, z)
        
        execution_time = time.time() - start_time
        
        # Calculate metrics
        B_cur = self.calculate_storage_used(z_j)
        mat_list = [j for j in range(len(z_j)) if z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)
        
        # Create result
        result = self.create_result(
            y_ij=y_ij,
            z_j=z_j,
            obj_val=obj_val,
            execution_time=execution_time,
            storage_used=B_cur,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
            initialization='utility_capacity_greedy'
        )
        
        return result
