"""BigSubs ILP optimization algorithm.

This module implements the BigSubs algorithm which uses randomized
initialization and iterative refinement with local ILP solving.
"""

import random
import time

import gurobipy as gp

from ..core.models import OptimizationResult
from .base import BaseILPOptimizer


class BigSubsOptimizer(BaseILPOptimizer):
    """BigSubs optimization with randomized search and local ILP.

    This algorithm uses:
    1. Random initialization of MV candidates
    2. Iterative refinement based on flip probabilities
    3. Local ILP solving for each query's edge labeling
    """

    def __init__(self, *args, **kwargs):
        """Initialize BigSubs optimizer.

        Args:
            *args: Positional arguments for BaseILPOptimizer
            **kwargs: Keyword arguments for BaseILPOptimizer
        """
        # Extract BigSubs-specific parameters before calling super().__init__
        self.U_j_max = kwargs.pop("U_j_max", None)
        self.U_max = kwargs.pop("U_max", 0.0)
        self.y_ij_init = kwargs.pop("y_ij", None)

        # Call parent constructor with remaining kwargs
        super().__init__(*args, **kwargs)

        # Set defaults if not provided
        if self.U_j_max is None:
            self.U_j_max = [0] * self.s_num
        if self.y_ij_init is None:
            self.y_ij_init = [[0] * self.s_num for _ in range(len(self.u_ij))]

    def initialize_random(self, mv_list: list[int]) -> list[int]:
        """Create random initial MV selection.

        Args:
            mv_list: Initial list (all zeros)

        Returns:
            Randomized MV selection
        """
        k = random.randint(1, len(mv_list))
        k_list = random.sample(range(len(mv_list)), k)
        for i in k_list:
            mv_list[i] = 1
        return mv_list

    def flip_probability(
        self,
        iter_num: int,
        z_j: int,
        b_j: int,
        B_cur: float,
        U_cur: float,
        U_j_cur: float,
        U_j_max: float,
        U_max: float,
        B_max: float,
    ) -> float:
        """Calculate probability of flipping a node's materialization status.

        Args:
            iter_num: Current iteration number
            z_j: Current materialization status
            b_j: Size of node j
            B_cur: Current storage used
            U_cur: Current total utility
            U_j_cur: Current utility of node j
            U_j_max: Maximum possible utility of node j
            U_max: Maximum possible total utility
            B_max: Storage budget

        Returns:
            Flip probability between 0 and 1
        """
        p = 10  # Iteration threshold

        # Capacity component
        if B_cur < B_max:
            p_j_capacity = 1 - (B_cur / B_max)
        else:
            p_j_capacity = 1 - (B_max / B_cur)

        # Utility component
        if z_j == 1:
            # If currently materialized, consider removing
            if U_cur > 0:
                p_j_utility = 1 - (U_j_cur / U_cur)
            else:
                p_j_utility = 0
        elif iter_num <= p or B_cur <= B_max - b_j:
            # If not materialized, consider adding
            if U_max > 0 and B_max > 0:
                utility_density_j = U_j_max / b_j if b_j > 0 else 0
                avg_utility_density = U_max / B_max
                p_j_utility = (
                    utility_density_j / avg_utility_density if avg_utility_density > 0 else 0
                )
            else:
                p_j_utility = 0
        else:
            p_j_utility = 0

        return p_j_capacity * p_j_utility

    def do_flip(self, probability: float, current_z: int) -> int:
        """Decide whether to flip based on probability.

        Args:
            probability: Flip probability
            current_z: Current status (0 or 1)

        Returns:
            New status (0 or 1)
        """
        t = random.random()
        if probability > t:
            return 1 - current_z  # Flip
        else:
            return current_z  # Keep

    def local_ilp(self, u_ij_row: list[float], k: list[int]) -> list[int]:
        """Solve local ILP for a single query.

        Args:
            u_ij_row: Utility values for one query
            k: Candidate MV indices for this query

        Returns:
            Binary selection of MVs for this query
        """
        if not k:
            return [0] * len(self.b_j)

        # Build local model
        model = gp.Model("local_ilp")
        model.Params.OutputFlag = 0

        # Variables
        y = {}
        for j in range(len(self.b_j)):
            y[j] = model.addVar(vtype=gp.GRB.BINARY, name=f"y_{j}")

        model.update()

        # Objective: maximize utility minus maintenance cost
        model.setObjective(
            gp.quicksum(u_ij_row[j] * y[j] - self.m_cost[j] * y[j] for j in k), gp.GRB.MAXIMIZE
        )

        # Constraints: overlapping subexpression
        for i in k:
            k_minus = [s for s in k if s != i]
            if k_minus:
                model.addConstr(
                    y[i] + gp.quicksum(y[j] * self.X[i][j] for j in k_minus) / len(self.b_j) <= 1
                )

        model.optimize()

        # Extract solution
        y_opt = [0] * len(self.b_j)
        for j in range(len(self.b_j)):
            y_opt[j] = int(y[j].X)

        return y_opt

    def initialize_candidates(self, **kwargs) -> tuple[list[int], list[int]]:
        """Initialize MV candidates (not used in BigSubs).

        BigSubs uses its own initialization through the optimize method.

        Returns:
            Empty lists (not used)
        """
        return [], []

    def optimize(self, iter_max: int = 3, **kwargs) -> OptimizationResult:
        """Execute the BigSubs optimization algorithm.

        Args:
            iter_max: Maximum number of iterations
            **kwargs: Additional arguments

        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        start_time = time.time()

        # Initialize random MV selection
        z_j = [0] * self.s_num
        z_j = self.initialize_random(z_j)

        # Calculate initial storage
        B_cur = sum(z_j[j] * self.b_j[j] for j in range(len(z_j)))

        # Iteration variables
        iter_num = 0
        updated = 1
        U_cur = 1.0
        U_j_cur = [0.0] * len(z_j)
        best_u = 0.0
        best_b = 0.0
        best_y_ij = self.y_ij_init
        best_z_j = z_j.copy()

        y_ij = [list(row) for row in self.y_ij_init]

        # Iterative refinement
        while updated == 1 and iter_num < iter_max:
            updated = 0

            # Vertex labeling: decide which nodes to materialize
            for j in range(len(z_j)):
                p_flip = self.flip_probability(
                    iter_num,
                    z_j[j],
                    self.b_j[j],
                    B_cur,
                    U_cur,
                    U_j_cur[j],
                    self.U_j_max[j],
                    self.U_max,
                    self.B_max,
                )
                z_j_new = self.do_flip(p_flip, z_j[j])

                if z_j_new != z_j[j]:
                    updated = 1
                    if z_j_new == 0:
                        B_cur -= self.b_j[j]
                    else:
                        B_cur += self.b_j[j]

                z_j[j] = z_j_new

            # Edge labeling: assign MVs to queries
            U_cur = 0.0
            U_j_cur = [0.0] * len(z_j)
            z_j_new = [0] * len(z_j)

            for i in range(len(self.q_s_list)):
                # Find candidates for this query
                M_i = [j for j in range(len(z_j)) if self.u_ij[i][j] > 0]
                M_i_ = [j for j in range(len(z_j)) if z_j[j] > 0]
                k = list(set(M_i) & set(M_i_))

                # Solve local ILP for this query
                y_ij[i] = self.local_ilp(self.u_ij[i], k)

                # Update utilities
                for j in k:
                    if y_ij[i][j] == 1 and z_j_new[j] == 0:
                        U_cur += self.u_ij[i][j] * y_ij[i][j] - self.m_cost[j] / len(self.q_s_list)
                        z_j_new[j] = 1
                    U_j_cur[j] += self.u_ij[i][j] * y_ij[i][j]

            # Update z_j and deduct maintenance costs
            for j in range(len(z_j)):
                z_j[j] = z_j_new[j]
                U_cur -= self.m_cost[j] * z_j[j]

            iter_num += 1

            # Track best solution
            if U_cur > best_u:
                best_u = U_cur
                best_b = B_cur
                best_y_ij = [list(row) for row in y_ij]
                best_z_j = z_j.copy()

        execution_time = time.time() - start_time

        # Get materialized view list
        mat_list = [j for j in range(len(best_z_j)) if best_z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)

        # Create result
        result = self.create_result(
            y_ij=best_y_ij,
            z_j=best_z_j,
            obj_val=best_u,
            execution_time=execution_time,
            storage_used=best_b,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
            iterations=iter_num,
        )

        return result
