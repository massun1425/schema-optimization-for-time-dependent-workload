"""BigSubs ILP optimization algorithm.

This module implements the BigSubs algorithm which uses randomized
initialization and iterative refinement with local ILP solving.
"""

import logging
import random
import time

import gurobipy as gp

logger = logging.getLogger(__name__)

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
        p = 160  # Iteration threshold

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

    def optimize(self, iter_max: int = 50, **kwargs) -> OptimizationResult:
        """Execute the BigSubs optimization algorithm.

        Args:
            iter_max: Maximum number of iterations
            **kwargs: Additional arguments

        Returns:
            OptimizationResult containing selected MVs and metrics
        """
        start_time = time.time()
        
        # Initialize convergence tracking
        self._convergence_history = []
        
        # Log header
        logger.info("="*60)
        logger.info("BigSubs Optimization - Convergence Tracking")
        logger.info(f"iter_max={iter_max}, B_max={self.B_max/1024/1024:.2f}MB, MV候補数={self.s_num}")
        logger.info("="*60)
        logger.info(f"{'Iter':>5} | {'Utility':>12} | {'Storage%':>10} | {'MV数':>6} | {'Best':>5}")
        logger.info("-"*60)

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

            # B_cur を z_j に合わせて正しく再計算する
            # Edge Labelingで使われなかったMVが削除されるため、B_curも更新が必要
            B_cur = sum(z_j[j] * self.b_j[j] for j in range(len(z_j)))

            iter_num += 1

            # Track convergence history
            storage_percent = (B_cur / self.B_max * 100) if self.B_max > 0 else 0
            mv_count = sum(z_j)
            is_best = U_cur > best_u and B_cur <= self.B_max
            
            self._convergence_history.append({
                'iteration': iter_num,
                'utility': U_cur,
                'storage': B_cur,
                'storage_percent': storage_percent,
                'mv_count': mv_count,
                'is_best': is_best
            })
            
            # Log progress (every 10 iterations or when best is updated)
            if iter_num <= 5 or iter_num % 10 == 0 or is_best:
                best_mark = "*" if is_best else ""
                logger.info(f"{iter_num:>5} | {U_cur:>12.2f} | {storage_percent:>9.2f}% | {mv_count:>6} | {best_mark:>5}")

            # Track best solution (容量制約を満たしている場合のみベストを更新)
            if U_cur > best_u and B_cur <= self.B_max:
                best_u = U_cur
                best_b = B_cur
                best_y_ij = [list(row) for row in y_ij]
                best_z_j = z_j.copy()

        execution_time = time.time() - start_time

        # Log summary
        best_iterations = [h['iteration'] for h in self._convergence_history if h['is_best']]
        last_best_iter = max(best_iterations) if best_iterations else 0
        
        logger.info("-"*60)
        logger.info(f"{'Finished':>5} | 総イテレーション: {iter_num}, 最終ベスト更新: iter {last_best_iter}")
        logger.info(f"{'Result':>5} | Utility: {best_u:.2f}, Storage: {best_b/1024/1024:.2f}MB ({best_b/self.B_max*100:.2f}%)")
        logger.info(f"{'':>5} | 選択MV数: {sum(best_z_j)}, 実行時間: {execution_time:.2f}秒")
        logger.info("="*60)

        # Get materialized view list
        mat_list = [j for j in range(len(best_z_j)) if best_z_j[j] == 1]
        mat_node_names = self.make_nodename_from_id(mat_list)

        # Create result with convergence summary
        convergence_summary = {
            'total_iterations': iter_num,
            'best_iterations': best_iterations,
            'last_best_iteration': last_best_iter,
            'recommended_iter_max': last_best_iter + 20 if last_best_iter > 0 else iter_max,
        }
        
        result = self.create_result(
            y_ij=best_y_ij,
            z_j=best_z_j,
            obj_val=best_u,
            execution_time=execution_time,
            storage_used=best_b,
            materialized_count=len(mat_list),
            materialized_nodes=mat_node_names,
            iterations=iter_num,
            convergence_summary=convergence_summary,
        )

        return result
