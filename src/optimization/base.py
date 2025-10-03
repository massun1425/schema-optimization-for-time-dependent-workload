"""Base class for ILP optimization algorithms.

This module provides the abstract base class that all ILP optimization
algorithms inherit from, defining common interfaces and shared functionality.
"""

from abc import ABC, abstractmethod
from typing import List, Tuple, Dict, Any, Optional
import gurobipy as gp
import copy

from ..core.query_manager import QueryManager
from ..core.models import OptimizationResult, MaterializedView
from config.settings import Settings


class BaseILPOptimizer(ABC):
    """Abstract base class for ILP-based materialized view selection.
    
    This class provides common functionality for all ILP optimization algorithms,
    including Gurobi model creation, constraint handling, and result processing.
    
    Attributes:
        qm: QueryManager instance containing query node information
        settings: Configuration settings
        s_num: Total number of subquery nodes
        m_cost: Maintenance cost for each node
        node_list: List of all node IDs
        B_max: Maximum storage budget
        b_j: Storage size for each node
        u_ij: Utility matrix [query_id][node_id]
        X: Inclusive dependency matrix
        q_s_list: Binary matrix of query-to-subquery relationships
        model: Gurobi optimization model
    """
    
    def __init__(
        self,
        qm: QueryManager,
        s_num: int,
        m_cost: List[float],
        node_list: List[str],
        B_max: float,
        b_j: List[int],
        u_ij: List[List[float]],
        X: List[List[int]],
        q_s_list: List[List[int]],
        settings: Optional[Settings] = None
    ) -> None:
        """Initialize the optimizer.
        
        Args:
            qm: QueryManager instance
            s_num: Total number of subquery nodes
            m_cost: Maintenance cost for each node
            node_list: List of all node IDs
            B_max: Maximum storage budget
            b_j: Storage size for each node
            u_ij: Utility matrix
            X: Dependency matrix
            q_s_list: Query-subquery relationship matrix
            settings: Configuration settings (optional)
        """
        self.qm = qm
        self.settings = settings or Settings()
        self.s_num = s_num
        self.m_cost = m_cost
        self.node_list = node_list
        self.B_max = B_max
        self.b_j = b_j
        self.u_ij = u_ij
        self.X = X
        self.q_s_list = q_s_list
        self.model: Optional[gp.Model] = None
    
    def build_ilp_model(
        self,
        cand_i: List[int],
        cand_j: List[int]
    ) -> Tuple[Dict, Dict]:
        """Build the ILP model with decision variables and constraints.
        
        Creates a Gurobi model with:
        - y[i,j]: Binary variable indicating if query i uses MV j
        - z[j]: Binary variable indicating if MV j is materialized
        
        Args:
            cand_i: List of query indices that are MV candidates
            cand_j: List of subquery indices that are MV candidates
            
        Returns:
            Tuple of (y_variables, z_variables)
        """
        self.model = gp.Model(f"{self.__class__.__name__}")
        self.model.Params.OutputFlag = 0
        
        # Decision variables
        y = {}
        for i in range(len(self.u_ij)):
            for j in range(len(self.b_j)):
                y[i, j] = self.model.addVar(
                    vtype=gp.GRB.BINARY,
                    name=f"y_{i}_{j}"
                )
        
        z = {}
        for j in range(len(self.b_j)):
            z[j] = self.model.addVar(
                vtype=gp.GRB.BINARY,
                name=f"z_{j}"
            )
        
        self.model.update()
        
        return y, z
    
    def add_common_constraints(
        self,
        y: Dict,
        z: Dict,
        cand_i: List[int],
        cand_j: List[int]
    ) -> None:
        """Add common constraints to the ILP model.
        
        Adds:
        1. Overlapping subexpression constraints
        2. Materialization dependency constraints (y[i,j] <= z[j])
        3. Storage budget constraint
        
        Args:
            y: Query-MV usage variables
            z: MV materialization variables
            cand_i: Candidate query indices
            cand_j: Candidate subquery indices
        """
        # Overlapping subexpression constraints
        for i in range(len(self.u_ij)):
            for j in range(len(self.b_j)):
                # If y[i,j]=1, then none of j's dependencies can be used
                self.model.addConstr(
                    y[i, j] + gp.quicksum(
                        y[i, u] * self.X[j][u] for u in range(len(self.b_j))
                    ) / len(self.b_j) <= 1
                )
                
                # y[i,j] can only be 1 if z[j]=1
                self.model.addConstr(y[i, j] <= z[j])
        
        # Storage budget constraint
        self.model.addConstr(
            gp.quicksum(self.b_j[j] * z[j] for j in range(len(self.b_j))) <= self.B_max
        )
    
    def set_objective(
        self,
        y: Dict,
        z: Dict,
        cand_i: List[int],
        cand_j: List[int]
    ) -> None:
        """Set the optimization objective function.
        
        Maximizes: total utility - maintenance cost
        
        Args:
            y: Query-MV usage variables
            z: MV materialization variables
            cand_i: Candidate query indices
            cand_j: Candidate subquery indices
        """
        self.model.setObjective(
            gp.quicksum(
                self.u_ij[i][j] * y[i, j]
                for i in range(len(cand_i))
                for j in range(len(cand_j))
            ) - gp.quicksum(
                z[j] * self.m_cost[j]
                for j in range(len(cand_j))
            ),
            gp.GRB.MAXIMIZE
        )
    
    def solve_ilp(
        self,
        y: Dict,
        z: Dict
    ) -> Tuple[List[List[int]], List[int], float]:
        """Solve the ILP model and extract results.
        
        Args:
            y: Query-MV usage variables
            z: MV materialization variables
            
        Returns:
            Tuple of (y_ij solution, z_j solution, objective value)
        """
        if self.model is None:
            raise RuntimeError("Model not built. Call build_ilp_model first.")
        
        self.model.optimize()
        
        # Extract solution
        ret_y = [[0] * len(self.b_j) for _ in range(len(self.u_ij))]
        ret_z = [0] * len(self.b_j)
        
        for j in range(len(self.b_j)):
            ret_z[j] = int(z[j].X)
            for i in range(len(self.u_ij)):
                ret_y[i][j] = int(y[i, j].X)
        
        obj_val = self.model.objVal
        
        return ret_y, ret_z, obj_val
    
    def make_nodename_from_id(
        self,
        x_list: List[int]
    ) -> List[str]:
        """Convert node indices to node names.
        
        Args:
            x_list: List of node indices
            
        Returns:
            List of node names
        """
        return [self.node_list[i] for i in x_list]
    
    def calculate_storage_used(self, z_j: List[int]) -> float:
        """Calculate total storage used by selected MVs.
        
        Args:
            z_j: Binary list indicating which MVs are materialized
            
        Returns:
            Total storage in bytes
        """
        return sum(self.b_j[j] * z_j[j] for j in range(len(z_j)))
    
    def get_materialized_views(
        self,
        z_j: List[int]
    ) -> List[MaterializedView]:
        """Create MaterializedView objects from solution.
        
        Args:
            z_j: Binary list indicating which MVs are materialized
            
        Returns:
            List of MaterializedView objects
        """
        mvs = []
        for j in range(len(z_j)):
            if z_j[j] == 1:
                node_id = self.node_list[j]
                mv = MaterializedView(
                    view_id=f"mv_{node_id}",
                    node_id=node_id,
                    create_sql="",  # To be filled by query rewriter
                    size=self.b_j[j],
                    maintenance_cost=self.m_cost[j],
                    usage_positions=self.qm.subquery_positions.get(node_id, [])
                )
                mvs.append(mv)
        return mvs
    
    @abstractmethod
    def initialize_candidates(
        self,
        **kwargs
    ) -> Tuple[List[int], List[int]]:
        """Initialize MV candidates (algorithm-specific).
        
        Different algorithms may have different strategies for
        selecting initial candidate sets.
        
        Returns:
            Tuple of (cand_i, cand_j) where:
                cand_i: Candidate query indices
                cand_j: Candidate subquery indices
        """
        pass
    
    @abstractmethod
    def optimize(self, **kwargs) -> OptimizationResult:
        """Run the optimization algorithm (algorithm-specific).
        
        This is the main entry point for each algorithm.
        Subclasses must implement their specific optimization logic.
        
        Returns:
            OptimizationResult with selected MVs and metrics
        """
        pass
    
    def create_result(
        self,
        y_ij: List[List[int]],
        z_j: List[int],
        obj_val: float,
        execution_time: float,
        **metadata
    ) -> OptimizationResult:
        """Create an OptimizationResult from algorithm output.
        
        Args:
            y_ij: Query-MV usage solution
            z_j: MV materialization solution
            obj_val: Objective function value
            execution_time: Time taken in seconds
            **metadata: Additional algorithm-specific metadata
            
        Returns:
            OptimizationResult object
        """
        selected_mvs = self.get_materialized_views(z_j)
        total_storage = self.calculate_storage_used(z_j)
        
        return OptimizationResult(
            algorithm=self.__class__.__name__,
            selected_views=selected_mvs,
            total_utility=obj_val,
            total_storage=total_storage,
            execution_time=execution_time,
            metadata={
                'y_ij': y_ij,
                'z_j': z_j,
                **metadata
            }
        )
