"""Two-step ILP optimizer with fixed MV support.

This module implements a 2-timestep ILP optimizer for adaptive MV selection.
It allows fixing the MVs at the first timestep and optimizing the second timestep.
"""

from __future__ import annotations

import logging
import time
from typing import Dict, List, Set, Optional

import gurobipy as gp

from core.sparse_structures import SparseMatrix

logger = logging.getLogger(__name__)


class TwoStepOptimizer:
    """
    Two-step ILP optimization with fixed MV support.

    This optimizer is designed for adaptive/sliding window optimization:
    - Timestep 0 (prev): MVs can be fixed to current configuration
    - Timestep 1 (curr): MVs are optimized based on current workload

    Objective (minimize):
        - Workload cost: -(benefit) weighted by query frequency
        - Migration cost: Cost of creating new MVs at timestep 1
    """

    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        prev_freq: List[float],
        curr_freq: List[float],
        migration_cost: Dict[int, float],
        fixed_mvs: Optional[Set[int]] = None,
        gurobi_output: int = 0,
        migration_cost_weight: float = 1.0,
    ) -> None:
        """
        Initialize the two-step optimizer.

        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J]
            X: Inclusion matrix [J][J]
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            prev_freq: Query frequencies for previous timestep
            curr_freq: Query frequencies for current timestep
            migration_cost: Fixed migration cost for each MV {j: cost}
            fixed_mvs: Set of MV indices that must be materialized at t=0.
                       None  -> t=0 is optimized freely (no fixing).
                       set() -> t=0 is fixed to NO MVs (build-from-empty init).
                       {..}  -> t=0 is fixed to the given configuration.
            gurobi_output: Gurobi log level (0=off, 1=on)
            migration_cost_weight: Weight for migration cost in objective
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.prev_freq = prev_freq
        self.curr_freq = curr_freq
        self.migration_cost = migration_cost
        # Distinguish None (optimize t=0 freely) from a set (fix t=0 to that set,
        # including the empty set which means "fix t=0 to no MVs").
        self._t0_fixed = fixed_mvs is not None
        self.fixed_mvs = fixed_mvs if fixed_mvs is not None else set()
        self.gurobi_output = gurobi_output
        self.migration_cost_weight = migration_cost_weight

        self.I = len(self.u_ij)  # Number of queries
        self.J = len(self.node_list)  # Number of MV candidates

        # Filter candidates with positive utility
        self.cand_j = self._initialize_candidates()

        # Sparse utility index: y[i,j,t] is created only when u_ij[i][j] > 0
        self.pos_js_by_i: Dict[int, List[int]] = {}
        self.pos_is_by_j: Dict[int, List[int]] = {}
        self._build_sparse_utility_index()

        self.model: gp.Model | None = None
        self.y: Dict[tuple, gp.Var] = {}  # y[i,j,t]: query i uses MV j at time t
        self.z: Dict[tuple, gp.Var] = {}  # z[j,t]: MV j exists at time t
        self.c: Dict[tuple, gp.Var] = {}  # c[j,t]: MV j is created at time t

        logger.debug(f"TwoStepOptimizer: I={self.I}, J={self.J}, candidates={len(self.cand_j)}")
        logger.debug(f"t=0 fixed: {self._t0_fixed} ({len(self.fixed_mvs)} MVs)")

    def _initialize_candidates(self) -> List[int]:
        """Filter candidates with positive utility."""
        if isinstance(self.u_ij, SparseMatrix):
            cset = set(self.fixed_mvs)
            for row in self.u_ij.rows.values():
                for j, v in row.items():
                    if v > 0:
                        cset.add(j)
            return sorted(cset)
        candidates = []
        for j in range(self.J):
            has_utility = any(self.u_ij[i][j] > 0 for i in range(self.I))
            # Also include MVs that are fixed (even if no utility)
            if has_utility or j in self.fixed_mvs:
                candidates.append(j)
        return candidates

    def _build_sparse_utility_index(self) -> None:
        """Build sparse index for positive-utility (i, j) pairs on candidates."""
        self.pos_js_by_i = {i: [] for i in range(self.I)}
        self.pos_is_by_j = {j: [] for j in self.cand_j}

        if isinstance(self.u_ij, SparseMatrix):
            cand_set = set(self.cand_j)
            for i, row in self.u_ij.rows.items():
                for j, v in row.items():
                    if v > 0 and j in cand_set:
                        self.pos_js_by_i[i].append(j)
                        self.pos_is_by_j[j].append(i)
            for i in self.pos_js_by_i:
                self.pos_js_by_i[i].sort()
            for j in self.pos_is_by_j:
                self.pos_is_by_j[j].sort()
        else:
            for i in range(self.I):
                for j in self.cand_j:
                    if self.u_ij[i][j] > 0:
                        self.pos_js_by_i[i].append(j)
                        self.pos_is_by_j[j].append(i)

    def _build_model(self) -> None:
        """Build the Gurobi model."""
        self.model = gp.Model("TwoStepMV")
        self.model.setParam("OutputFlag", self.gurobi_output)
        m = self.model

        # Variables for both timesteps (t=0: prev, t=1: curr)
        for t in [0, 1]:
            for i in range(self.I):
                for j in self.pos_js_by_i.get(i, []):  # Sparse y: only positive-utility pairs
                    self.y[i, j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}_{t}")

            for j in self.cand_j:
                if t == 0 and self._t0_fixed:
                    # Fixed at t=0: set z as constant (empty set => all zeros)
                    self.z[j, t] = 1 if j in self.fixed_mvs else 0
                else:
                    self.z[j, t] = m.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}_{t}")

        # Creation variables (only for t=1); relaxed to continuous — exact under c >= z1-z0, c <= 1
        for j in self.cand_j:
            self.c[j, 1] = m.addVar(vtype=gp.GRB.CONTINUOUS, lb=0.0, ub=1.0, name=f"c_{j}_1")

        m.update()

        # --- Objective ---
        workload_cost = gp.LinExpr()
        migration_cost_expr = gp.LinExpr()

        for t, freq in [(0, self.prev_freq), (1, self.curr_freq)]:
            for i in range(self.I):
                for j in self.pos_js_by_i.get(i, []):  # Sparse: only positive-utility pairs
                    benefit = self.u_ij[i][j] * freq[i]
                    y_var = self.y.get((i, j, t), 0)
                    if isinstance(y_var, gp.Var):
                        workload_cost -= benefit * y_var
                    elif y_var == 1:
                        workload_cost -= benefit

        # Migration cost at t=1
        for j in self.cand_j:
            cost = self.migration_cost.get(j, 0.0)
            if cost > 0:
                migration_cost_expr += cost * self.c[j, 1]

        m.setObjective(
            workload_cost + self.migration_cost_weight * migration_cost_expr,
            gp.GRB.MINIMIZE
        )

        # --- Constraints ---
        for t in [0, 1]:
            for i in range(self.I):
                for j in self.pos_js_by_i.get(i, []):  # Sparse: only positive-utility pairs
                    # y <= z (usage implies materialization)
                    z_val = self.z[j, t]
                    y_var = self.y.get((i, j, t))
                    if y_var is None:
                        continue
                    if isinstance(z_val, gp.Var):
                        m.addConstr(y_var <= z_val)
                    elif z_val == 0:
                        m.addConstr(y_var == 0)
                    # If z_val == 1, y is free (0 or 1)

        # NOTE: No "at most one MV per query" constraint. A query may benefit from
        # multiple non-overlapping MVs (benefits sum), matching TimeDependentOptimizer.

        # Storage constraint (skip t=0 only when it is fixed and assumed feasible)
        for t in [0, 1]:
            if t == 0 and self._t0_fixed:
                continue  # Skip - already fixed and assumed feasible
            storage_sum = gp.quicksum(
                self.b_j[j] * self.z[j, t]
                for j in self.cand_j
                if isinstance(self.z[j, t], gp.Var)
            )
            m.addConstr(storage_sum <= self.B_max)

        # Inclusion/overlap exclusion (y-level, per query) matching TimeDependentOptimizer:
        # a single query cannot use two overlapping MVs together, but both may be
        # materialized for different queries.
        for t in [0, 1]:
            for i in range(self.I):
                for j in self.pos_js_by_i.get(i, []):
                    y_var = self.y.get((i, j, t))
                    if y_var is None:
                        continue
                    overlap = gp.quicksum(
                        self.y[i, u, t] * self.X[j][u]
                        for u in self.pos_js_by_i.get(i, [])
                        if u != j and self.X[j][u] != 0 and (i, u, t) in self.y
                    )
                    m.addConstr(
                        y_var + overlap / max(1, len(self.cand_j)) <= 1
                    )

        # Creation flag: c[j,1] = max(0, z[j,1] - z[j,0])
        for j in self.cand_j:
            z_0 = self.z[j, 0]
            z_1 = self.z[j, 1]
            if isinstance(z_1, gp.Var):
                if isinstance(z_0, gp.Var):
                    m.addConstr(self.c[j, 1] >= z_1 - z_0)
                elif z_0 == 0:
                    m.addConstr(self.c[j, 1] >= z_1)
                else:  # z_0 == 1
                    m.addConstr(self.c[j, 1] >= z_1 - 1)
            m.addConstr(self.c[j, 1] <= 1)

    def optimize(self) -> Dict:
        """
        Run the optimization.

        Returns:
            Dictionary with:
                - selected_mvs_t0: Set of MV indices at t=0
                - selected_mvs_t1: Set of MV indices at t=1
                - objective: Objective value
                - solve_time_sec: Solve time
        """
        start_time = time.time()
        self._build_model()
        self.model.optimize()

        solve_time = time.time() - start_time

        if self.model.Status != gp.GRB.OPTIMAL:
            logger.warning(f"Optimization status: {self.model.Status}")
            # Return fixed MVs if infeasible
            return {
                "selected_mvs_t0": self.fixed_mvs,
                "selected_mvs_t1": self.fixed_mvs,
                "objective": float('inf'),
                "solve_time_sec": solve_time,
                "status": self.model.Status,
            }

        # Extract solution
        selected_t0 = set()
        selected_t1 = set()

        for j in self.cand_j:
            z_0 = self.z[j, 0]
            z_1 = self.z[j, 1]
            if isinstance(z_0, gp.Var):
                if z_0.X > 0.5:
                    selected_t0.add(j)
            elif z_0 == 1:
                selected_t0.add(j)

            if isinstance(z_1, gp.Var):
                if z_1.X > 0.5:
                    selected_t1.add(j)
            elif z_1 == 1:
                selected_t1.add(j)

        return {
            "selected_mvs_t0": selected_t0,
            "selected_mvs_t1": selected_t1,
            "objective": self.model.ObjVal,
            "solve_time_sec": solve_time,
            "status": self.model.Status,
        }
