"""CF (MV) Pruner using Workload Summary Tree.

This module implements the CF pruning algorithm (Algorithm 1 & 2) from
Section 4.3 of the paper. It uses a Workload Summary Tree to hierarchically
divide the optimization problem and identify promising MV candidates.

The pruning works by:
1. Building a Workload Summary Tree
2. Recursively solving local ILPs at each tree node (3 timesteps only)
3. Propagating boundary constraints from parent to children
4. Collecting all MVs that appear in any local solution as "promising"
5. Filtering the full candidate set to only promising MVs

Boundary Constraint Mechanism (Section 4.3.2):
---------------------------------------------
Parent-to-child constraints ensure that the MV sets at boundary timesteps
are IDENTICAL (complete match, not subset). This maintains global consistency
while allowing local optimization.

- Left child (first half):
  - min timestep: Fixed to parent's min MV set
  - max timestep: Fixed to parent's median MV set
  - median timestep: Free to optimize
  
- Right child (second half):
  - min timestep: Fixed to parent's median MV set
  - max timestep: Fixed to parent's max MV set
  - median timestep: Free to optimize

This "pin both ends, optimize the middle" approach ensures:
1. Global consistency: Preserves high-level schema flow from parent
2. Search space reduction: Limits valid transitions, speeding up computation
"""

from __future__ import annotations

import logging
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Set, Tuple, Optional

import gurobipy as gp

from core.local_ilp_optimizer import LocalILPOptimizer
from core.sparse_structures import (
    SparseMatrix,
    SparseMatrixBase,
    SparseXBase,
    SharedSparseMatrix,
    SharedSparseX,
    build_u_csr,
    build_x_csr,
    put_array_to_shm,
    attach_array_from_shm,
)
from core.workload_summary_tree import (
    TreeNode,
    WorkloadSummaryTree,
)

logger = logging.getLogger(__name__)


class CFPruner:
    """CF (MV) candidate pruner using Workload Summary Tree.
    
    This class implements the pruning algorithm to reduce the number of
    MV candidates before running the full time-dependent optimization.
    
    By solving many small local ILPs (3 timesteps each) instead of one
    large ILP (all timesteps), we can quickly identify which MVs are
    promising and filter out the rest.
    """
    
    def __init__(
        self,
        node_list: List[str],
        u_ij: List[List[float]],
        X: List[List[int]],
        b_j: List[float],
        B_max: float,
        timesteps: List[str],
        migration_cost: Dict[int, float],
        query_frequency_by_timestep: Dict[str, List[float]],
        gurobi_output: int = 0,
        use_parallel: bool = False,
        max_workers: Optional[int] = 16,
        inherit_parent_constraints: bool = True,
    ):
        """Initialize the CF pruner.

        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J]
            X: Inclusion matrix [J][J]
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            timesteps: List of timestep names
            migration_cost: Fixed migration cost for each MV {j: cost}
            query_frequency_by_timestep: Query frequencies for each timestep
            gurobi_output: Gurobi log level (0=off, 1=on)
            use_parallel: Enable parallel processing (default: False)
            max_workers: Maximum number of worker processes (default: CPU count)
            inherit_parent_constraints: Propagate parent boundary constraints to child nodes (default: True)
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.timesteps = timesteps
        self.migration_cost = migration_cost
        self.freq = query_frequency_by_timestep
        self.gurobi_output = gurobi_output
        self.inherit_parent_constraints = inherit_parent_constraints
        
        self.I = len(u_ij)  # Number of queries
        self.T = len(timesteps)
        self.J = len(node_list)
        
        # Build the Workload Summary Tree
        self.tree = WorkloadSummaryTree(self.T)

        # Pre-compute candidates once (optimization to avoid redundant filtering)
        # This is the same logic as TimeDependentOptimizer.initialize_candidates()
        self.cand_j = self._initialize_candidates()

        # Parallel processing settings
        self.use_parallel = use_parallel
        if max_workers is None:
            self.max_workers = multiprocessing.cpu_count()
        else:
            self.max_workers = max_workers

        logger.info(
            f"CFPruner initialized: T={self.T}, J={self.J}, "
            f"candidates={len(self.cand_j)}, "
            f"tree_depth={self.tree.get_depth()}, tree_nodes={len(self.tree.get_all_nodes())}, "
            f"parallel={self.use_parallel}, workers={self.max_workers if self.use_parallel else 'N/A'}"
        )
    
    def _initialize_candidates(self) -> List[int]:
        """Initialize MV candidates based on utility (same as TimeDependentOptimizer).
        
        Returns only nodes that have positive utility for at least one query.
        This is computed once and shared across all LocalILP instances.
        """
        if isinstance(self.u_ij, SparseMatrix):
            cset = set()
            for row in self.u_ij.rows.values():
                for j, v in row.items():
                    if v > 0:
                        cset.add(j)
            candidates = sorted(cset)
        else:
            candidates = []
            for j in range(self.J):
                has_utility = any(self.u_ij[i][j] > 0 for i in range(self.I))
                if has_utility:
                    candidates.append(j)

        logger.info(f"Filtered to {len(candidates)} candidates (from {self.J} total nodes)")
        return candidates
    
    def _solve_static_optimization(self) -> Set[int]:
        """Solve static optimization using average frequencies across all timesteps.
        
        This implements the "static protection" approach: MVs selected by static
        optimization (using global average frequencies) are considered "protected"
        and should not be pruned.
        
        Returns:
            Set of MV indices selected by static optimization
        """
        logger.info("Solving static optimization for protected MV set...")
        
        # Calculate average frequencies across all timesteps
        avg_freq = [0.0] * self.I
        for ts in self.timesteps:
            for i in range(self.I):
                avg_freq[i] += self.freq[ts][i]
        avg_freq = [f / self.T for f in avg_freq]
        
        # Build weighted utility: u_ij * avg_freq[i]
        weighted_u_ij = []
        for i in range(self.I):
            weighted_row = [self.u_ij[i][j] * avg_freq[i] for j in range(self.J)]
            weighted_u_ij.append(weighted_row)
        
        # Solve static ILP (single timestep, no migration cost)
        model = gp.Model("StaticILP")
        model.Params.OutputFlag = self.gurobi_output
        
        try:
            # Variables: z[j] = 1 if MV j is selected
            z = {}
            for j in self.cand_j:
                z[j] = model.addVar(vtype=gp.GRB.BINARY, name=f"z_{j}")
            
            # Variables: y[i,j] = 1 if query i uses MV j
            y = {}
            for i in range(self.I):
                for j in self.cand_j:
                    y[i, j] = model.addVar(vtype=gp.GRB.BINARY, name=f"y_{i}_{j}")
            
            model.update()
            
            # Constraint: Usage implies materialization (y[i,j] <= z[j])
            for i in range(self.I):
                for j in self.cand_j:
                    model.addConstr(y[i, j] <= z[j], name=f"use_le_mat_{i}_{j}")
            
            # Constraint: Inclusion/overlap exclusion
            # Note: Normalization by len(cand_j) matches NormalOptimizer behavior
            for i in range(self.I):
                for j in self.cand_j:
                    model.addConstr(
                        y[i, j] + gp.quicksum(
                            y[i, u] * self.X[j][u]
                            for u in self.cand_j if u != j
                        ) / len(self.cand_j) <= 1,
                        name=f"inclusive_excl_{i}_{j}"
                    )
            
            # Constraint: Storage budget
            model.addConstr(
                gp.quicksum(self.b_j[j] * z[j] for j in self.cand_j) <= self.B_max,
                name="storage"
            )
            
            # Objective: Maximize total utility (minimize negative)
            objective = gp.quicksum(
                -weighted_u_ij[i][j] * y[i, j]
                for i in range(self.I)
                for j in self.cand_j
            )
            model.setObjective(objective, gp.GRB.MINIMIZE)
            
            # Solve
            model.optimize()
            
            # Extract selected MVs
            static_mvs = set()
            if model.status == gp.GRB.OPTIMAL:
                for j in self.cand_j:
                    if z[j].X > 0.5:
                        static_mvs.add(j)
            
            logger.info(f"Static optimization selected {len(static_mvs)} MVs")
            return static_mvs
            
        finally:
            model.dispose()
    
    def prune_candidates(self, use_static_protection: bool = False) -> Set[int]:
        """Execute the pruning algorithm and return promising MV indices.
        
        This is the main entry point for pruning. It:
        1. (Optional) Solves static optimization for protected MVs
        2. Recursively traverses the Workload Summary Tree
        3. Solves local ILPs at each node
        4. Collects all MVs that appear in any solution
        5. Merges static protected MVs with local results
        6. Returns the set of promising MV indices
        
        Args:
            use_static_protection: If True, merge static optimization results
                with local pruning results (default: False)
        
        Returns:
            Set of promising MV indices (subset of [0, J-1])
        """
        logger.info("=" * 70)
        logger.info("Starting CF Pruning with Workload Summary Tree")
        logger.info("=" * 70)
        logger.info(f"Total timesteps: {self.T}")
        logger.info(f"Total MV candidates: {self.J}")
        logger.info(f"Filtered candidates: {len(self.cand_j)}")
        logger.info(f"Tree depth: {self.tree.get_depth()}")
        logger.info(f"Tree nodes: {len(self.tree.get_all_nodes())}")
        logger.info(f"Mode: {'Parallel' if self.use_parallel else 'Sequential'}")
        logger.info(f"Static protection: {'Enabled' if use_static_protection else 'Disabled'}")
        if self.use_parallel:
            logger.info(f"Workers: {self.max_workers}")
        logger.info("-" * 70)
        
        # Solve static optimization for protected MVs (if enabled)
        static_protected_mvs: Set[int] = set()
        if use_static_protection:
            static_protected_mvs = self._solve_static_optimization()
            logger.info(f"Static protected MVs: {len(static_protected_mvs)}")
        
        # Choose parallel or sequential execution for local pruning
        if self.use_parallel:
            promising_mvs = self._prune_candidates_parallel()
        else:
            promising_mvs = self._prune_candidates_sequential()
        
        # Merge static protected MVs with local results
        local_only_count = len(promising_mvs)
        if use_static_protection:
            promising_mvs.update(static_protected_mvs)
            added_by_static = len(promising_mvs) - local_only_count
            logger.info(f"After merging static protected: {len(promising_mvs)} MVs (+{added_by_static} from static)")
        
        logger.info("-" * 70)
        logger.info(f"CF Pruning Completed!")
        logger.info(f"Promising MVs: {len(promising_mvs)}/{self.J}")
        logger.info(f"Reduction: {100.0 * (1 - len(promising_mvs) / self.J):.1f}%")
        logger.info("=" * 70)
        
        # Store static protected MVs for later reference
        self.static_protected_mvs = static_protected_mvs
        
        return promising_mvs
    
    def _prune_candidates_sequential(self) -> Set[int]:
        """Sequential (original) implementation of pruning."""
        # Collect promising MVs from all tree nodes
        promising_mvs: Set[int] = set()
        
        # Track statistics
        self.node_count = 0
        self.total_nodes = len(self.tree.get_all_nodes())
        
        # Start recursive traversal from root (no parent constraints)
        if self.tree.root:
            self._recursive_solve(
                node=self.tree.root,
                parent_min_mvs=set(),
                parent_max_mvs=set(),
                promising_mvs=promising_mvs,
                is_left_child=False,
                is_right_child=False,
            )
        
        return promising_mvs
    
    def _prune_candidates_parallel(self) -> Set[int]:
        """Parallel implementation using level-by-level BFS approach.
        
        Processes all nodes at the same tree level in parallel, then proceeds
        to the next level. This maintains parent-child dependency while
        maximizing parallelism.
        """
        promising_mvs: Set[int] = set()

        if not self.tree.root:
            return promising_mvs

        # Track statistics
        self.node_count = 0
        self.total_nodes = len(self.tree.get_all_nodes())

        # Use ONE persistent pool across levels. For the sparse backend, place
        # u_ij/X into shared memory ONCE and have workers attach (zero per-task
        # pickling, single physical copy, portable). Dense backend falls back to
        # the original per-task argument passing.
        sparse = isinstance(self.u_ij, SparseMatrixBase) and isinstance(self.X, SparseXBase)
        shms = []
        executor = None
        try:
            if sparse:
                logger.info("Parallel: building CSR + shared memory (one copy for all workers)...")
                u_indptr, u_col, u_data = build_u_csr(self.u_ij)
                x_indptr, x_idx = build_x_csr(self.X)
                specs = []
                for arr in (u_indptr, u_col, u_data, x_indptr, x_idx):
                    shm, spec = put_array_to_shm(arr)
                    shms.append(shm)
                    specs.append(spec)
                init_args = (
                    tuple(specs), self.I, self.J, self.node_list, self.b_j,
                    self.B_max, self.timesteps, self.migration_cost, self.freq,
                    self.cand_j, self.gurobi_output, self.inherit_parent_constraints,
                )
                executor = ProcessPoolExecutor(
                    max_workers=self.max_workers, initializer=_pp_init, initargs=init_args
                )

                def _submit(node, pmin, pmax, il, ir):
                    return executor.submit(_pp_solve, node, pmin, pmax, il, ir)
            else:
                executor = ProcessPoolExecutor(max_workers=self.max_workers)

                def _submit(node, pmin, pmax, il, ir):
                    return executor.submit(
                        _solve_node_static, node, pmin, pmax, il, ir,
                        self.node_list, self.u_ij, self.X, self.b_j, self.B_max,
                        self.timesteps, self.migration_cost, self.freq, self.cand_j,
                        self.gurobi_output, self.inherit_parent_constraints,
                    )

            # Level-by-level BFS: (node, parent_min, parent_max, is_left, is_right)
            current_level = [(self.tree.root, set(), set(), False, False)]
            while current_level:
                next_level = []
                future_to_node = {}
                for node, parent_min, parent_max, is_left, is_right in current_level:
                    future_to_node[_submit(node, parent_min, parent_max, is_left, is_right)] = node

                for future in as_completed(future_to_node):
                    node = future_to_node[future]
                    try:
                        result = future.result()
                        self.node_count += 1
                        progress = f"[{self.node_count}/{self.total_nodes}]"

                        optimal_mvs = result['selected_mvs']
                        pool_mvs = result.get('pool_mvs', set())
                        all_mvs = optimal_mvs.copy()
                        if pool_mvs:
                            all_mvs.update(pool_mvs)

                        before_count = len(promising_mvs)
                        promising_mvs.update(all_mvs)
                        new_mvs = len(promising_mvs) - before_count

                        logger.info(
                            f"{progress} Processing node: timesteps {result['timestep_indices']}, depth={node.depth}"
                        )
                        logger.info(
                            f"  ✓ Selected {len(all_mvs)} MVs "
                            f"(optimal: {len(optimal_mvs)}, pool: {len(pool_mvs)}, "
                            f"+{new_mvs} new, total: {len(promising_mvs)})"
                        )

                        if node.left_child:
                            next_level.append((node.left_child, result['min_mvs'], result['median_mvs'], True, False))
                        if node.right_child:
                            next_level.append((node.right_child, result['median_mvs'], result['max_mvs'], False, True))

                    except Exception as e:
                        logger.error(f"Error processing node: {e}")
                        import traceback
                        traceback.print_exc()

                current_level = next_level
        finally:
            if executor is not None:
                executor.shutdown(wait=True)   # workers finish/exit before unlink
            for shm in shms:
                try:
                    shm.close()
                    shm.unlink()
                except Exception:
                    pass

        return promising_mvs
    
    def _aggregate_frequencies(self, node: TreeNode) -> Dict[str, List[float]]:
        """Aggregate frequencies over the node's period into 3 representative timesteps.

        Splits [min_idx, max_idx] into 3 equal partitions and sums frequencies
        within each partition, assigning totals to min, median, max timesteps.
        When the period is too short to partition (duration < 3), the original
        per-timestep frequencies are used as-is.
        """
        start_idx = node.min_idx
        end_idx = node.max_idx
        duration = end_idx - start_idx

        aggregated_freq: Dict[str, List[float]] = {}
        num_queries = self.I

        if duration < 3:
            for t_idx in [node.min_idx, node.median_idx, node.max_idx]:
                ts_name = self.timesteps[t_idx]
                aggregated_freq[ts_name] = self.freq[ts_name]
            return aggregated_freq

        partition_size = duration / 3.0
        b1 = int(start_idx + partition_size)
        b2 = int(start_idx + partition_size * 2)

        ranges = [
            (start_idx, b1),
            (b1, b2),
            (b2, end_idx + 1),
        ]
        target_indices = [node.min_idx, node.median_idx, node.max_idx]

        for range_idx, (r_start, r_end) in enumerate(ranges):
            total_freqs = [0.0] * num_queries
            for t in range(r_start, r_end):
                if t >= len(self.timesteps):
                    continue
                ts_name = self.timesteps[t]
                for q in range(num_queries):
                    total_freqs[q] += self.freq[ts_name][q]
            target_ts_name = self.timesteps[target_indices[range_idx]]
            aggregated_freq[target_ts_name] = total_freqs

        return aggregated_freq

    def _recursive_solve(
        self,
        node: TreeNode,
        parent_min_mvs: Set[int],
        parent_max_mvs: Set[int],
        promising_mvs: Set[int],
        is_left_child: bool = False,
        is_right_child: bool = False,
    ) -> dict:
        """Recursively solve local ILP at a tree node and traverse children.
        
        According to the paper, boundary constraints ensure that:
        - Left child: min = parent.min, max = parent.median (both fixed)
        - Right child: min = parent.median, max = parent.max (both fixed)
        - The middle (median) timestep is free to optimize
        
        Args:
            node: Current tree node
            parent_min_mvs: MVs at parent's min (for left child's min constraint)
            parent_max_mvs: MVs at parent's max (for right child's max constraint)
            promising_mvs: Accumulator for all promising MVs (modified in-place)
            is_left_child: True if this is a left child (apply min constraint)
            is_right_child: True if this is a right child (apply max constraint)
            
        Returns:
            Dictionary with solution info including MVs at min, median, max
        """
        # Progress tracking
        self.node_count += 1
        progress = f"[{self.node_count}/{self.total_nodes}]"
        
        logger.info(f"{progress} Processing node: timesteps [{node.min_idx}, {node.median_idx}, {node.max_idx}], depth={node.depth}")
        
        # Prepare timestep indices for this node
        timestep_indices = [node.min_idx, node.median_idx, node.max_idx]
        
        # Prepare fixed MV constraints based on parent boundaries
        # Paper Section 4.3.2: "child node solves a local ILP so that the
        # optimized column families at the min/max time steps are identical
        # to the ones found at the same time steps in the parent workload"
        fixed_mvs_by_timestep: Dict[int, Set[int]] = {}

        if self.inherit_parent_constraints:
            # Left child: fix min to parent's min, max to parent's median
            if is_left_child and parent_min_mvs:
                fixed_mvs_by_timestep[node.min_idx] = parent_min_mvs.copy()
                logger.info(f"  → Left child: fixing min (t={node.min_idx}) with {len(parent_min_mvs)} MVs")
            if is_left_child and parent_max_mvs:
                # For left child, parent_max_mvs contains parent's median MVs
                fixed_mvs_by_timestep[node.max_idx] = parent_max_mvs.copy()
                logger.info(f"  → Left child: fixing max (t={node.max_idx}) with {len(parent_max_mvs)} MVs")

            # Right child: fix min to parent's median, max to parent's max
            if is_right_child and parent_min_mvs:
                # For right child, parent_min_mvs contains parent's median MVs
                fixed_mvs_by_timestep[node.min_idx] = parent_min_mvs.copy()
                logger.info(f"  → Right child: fixing min (t={node.min_idx}) with {len(parent_min_mvs)} MVs")
            if is_right_child and parent_max_mvs:
                fixed_mvs_by_timestep[node.max_idx] = parent_max_mvs.copy()
                logger.info(f"  → Right child: fixing max (t={node.max_idx}) with {len(parent_max_mvs)} MVs")
            
        # Aggregate frequencies over the node's period (same as UtilityPruner)
        aggregated_freq = self._aggregate_frequencies(node)

        # Create and solve local ILP
        local_optimizer = LocalILPOptimizer(
            node_list=self.node_list,
            u_ij=self.u_ij,
            X=self.X,
            b_j=self.b_j,
            B_max=self.B_max,
            timestep_indices=timestep_indices,
            all_timesteps=self.timesteps,
            migration_cost=self.migration_cost,
            query_frequency_by_timestep=aggregated_freq,
            fixed_mvs_by_timestep=fixed_mvs_by_timestep,
            candidate_indices=self.cand_j,  # pass the precomputed candidates
            gurobi_output=self.gurobi_output,
        )
        
        result = local_optimizer.optimize()
        
        # Extract selected MVs from optimal solution (for parent-child constraints)
        selected_mvs_optimal: Set[int] = set()
        for t_idx, mvs in result["selected_mvs_by_timestep"].items():
            selected_mvs_optimal.update(mvs)
        
        # Extract pool MVs if available (for pruning)
        pool_mvs = result.get("pool_mvs", set())
        
        # Combine optimal + pool for promising set (pruning purpose)
        selected_mvs_all = selected_mvs_optimal.copy()
        if pool_mvs:
            selected_mvs_all.update(pool_mvs)
            logger.info(f"  → Using Solution Pool: +{len(pool_mvs - selected_mvs_optimal)} additional MVs from pool")
        
        # Add to promising set
        before_count = len(promising_mvs)
        promising_mvs.update(selected_mvs_all)
        new_mvs = len(promising_mvs) - before_count
        
        logger.info(
            f"  ✓ Selected {len(selected_mvs_all)} MVs "
            f"(optimal: {len(selected_mvs_optimal)}, pool: {len(pool_mvs)}, "
            f"+{new_mvs} new, total: {len(promising_mvs)})"
        )
        
        # Extract MVs at each timestep for passing to children
        # IMPORTANT: Use optimal solution only for boundary constraints
        min_mvs = result["selected_mvs_by_timestep"].get(node.min_idx, set())
        median_mvs = result["selected_mvs_by_timestep"].get(node.median_idx, set())
        max_mvs = result["selected_mvs_by_timestep"].get(node.max_idx, set())

        
        # Recursively process children with correct boundary constraints
        # Left child: gets parent.min and parent.median as boundaries
        if node.left_child:
            self._recursive_solve(
                node=node.left_child,
                parent_min_mvs=min_mvs,      # Left child's min = parent's min
                parent_max_mvs=median_mvs,   # Left child's max = parent's median
                promising_mvs=promising_mvs,
                is_left_child=True,
                is_right_child=False,
            )
        
        # Right child: gets parent.median and parent.max as boundaries
        if node.right_child:
            self._recursive_solve(
                node=node.right_child,
                parent_min_mvs=median_mvs,   # Right child's min = parent's median
                parent_max_mvs=max_mvs,      # Right child's max = parent's max
                promising_mvs=promising_mvs,
                is_left_child=False,
                is_right_child=True,
            )
        
        return {
            "min_mvs": min_mvs,
            "median_mvs": median_mvs,
            "max_mvs": max_mvs,
        }
    
    def get_filtering_info(self, promising_mvs: Set[int]) -> dict:
        """Get information about the filtering results.
        
        Args:
            promising_mvs: Set of promising MV indices
        
        Returns:
            Dictionary with filtering statistics
        """
        static_protected = getattr(self, 'static_protected_mvs', set())
        return {
            "total_candidates": self.J,
            "promising_candidates": len(promising_mvs),
            "filtered_out": self.J - len(promising_mvs),
            "retention_rate": len(promising_mvs) / self.J if self.J > 0 else 0.0,
            "reduction_rate": 1.0 - (len(promising_mvs) / self.J) if self.J > 0 else 0.0,
            "promising_mv_names": [self.node_list[j] for j in sorted(promising_mvs)],
            "static_protected_count": len(static_protected),
            "static_protected_mv_names": [self.node_list[j] for j in sorted(static_protected)],
        }


# ==============================================================================
# Module-level functions / state for parallel processing
# ==============================================================================
# These must be at module level (not methods) to be pickle-able for
# ProcessPoolExecutor.

# Per-worker context (populated once by the initializer; read-only thereafter).
# Holds the shared-memory-backed u_ij/X and the small shared config, so tasks
# carry only (node, parent boundaries) instead of the huge matrices.
_PP_CTX: dict = {}


def _pp_init(specs, I, J, node_list, b_j, B_max, timesteps,
             migration_cost, freq, cand_j, gurobi_output, inherit) -> None:
    """Worker initializer: attach shared-memory CSR arrays once per worker."""
    s_uip, s_ucol, s_udat, s_xip, s_xidx = specs
    shms = []
    sh, u_indptr = attach_array_from_shm(s_uip); shms.append(sh)
    sh, u_col = attach_array_from_shm(s_ucol); shms.append(sh)
    sh, u_data = attach_array_from_shm(s_udat); shms.append(sh)
    sh, x_indptr = attach_array_from_shm(s_xip); shms.append(sh)
    sh, x_idx = attach_array_from_shm(s_xidx); shms.append(sh)
    _PP_CTX.clear()
    _PP_CTX.update(dict(
        u_ij=SharedSparseMatrix(u_indptr, u_col, u_data, I, J),
        X=SharedSparseX(x_indptr, x_idx, J),
        node_list=node_list, b_j=b_j, B_max=B_max, timesteps=timesteps,
        migration_cost=migration_cost, freq=freq, cand_j=cand_j,
        gurobi_output=gurobi_output, inherit=inherit, _shms=shms,
    ))


def _pp_solve(node, parent_min, parent_max, is_left, is_right) -> dict:
    """Worker task: solve one tree node using the shared-memory context."""
    c = _PP_CTX
    return _solve_node_static(
        node, parent_min, parent_max, is_left, is_right,
        c["node_list"], c["u_ij"], c["X"], c["b_j"], c["B_max"],
        c["timesteps"], c["migration_cost"], c["freq"], c["cand_j"],
        c["gurobi_output"], c["inherit"],
    )


def _solve_node_static(
    node: TreeNode,
    parent_min_mvs: Set[int],
    parent_max_mvs: Set[int],
    is_left_child: bool,
    is_right_child: bool,
    node_list: List[str],
    u_ij: List[List[float]],
    X: List[List[int]],
    b_j: List[float],
    B_max: float,
    timesteps: List[str],
    migration_cost: Dict[int, float],
    freq: Dict[str, List[float]],
    cand_j: List[int],
    gurobi_output: int,
    inherit_parent_constraints: bool = True,
) -> dict:
    """Solve local ILP for a single tree node (static function for parallel processing).
    
    This is a module-level function (not a class method) so it can be pickled
    and sent to worker processes.
    
    Args:
        node: Current tree node
        parent_min_mvs: MVs at parent's min boundary
        parent_max_mvs: MVs at parent's max boundary
        is_left_child: True if this is a left child
        is_right_child: True if this is a right child
        node_list: List of node IDs (MV candidates)
        u_ij: Utility matrix
        X: Inclusion matrix
        b_j: Storage sizes
        B_max: Storage budget
        timesteps: All timestep names
        migration_cost: Fixed migration cost for each MV
        freq: Query frequencies by timestep
        cand_j: Pre-filtered candidate indices
        gurobi_output: Gurobi log level
        
    Returns:
        Dictionary with solution info
    """
    # --- Change: split the interval into three equal parts and aggregate frequencies per part ---
    
    start_idx = node.min_idx
    end_idx = node.max_idx
    duration = end_idx - start_idx
    
    # Build a new frequency dict to pass to the solver
    # (the optimization only uses the three points min, median and max, so only those keys need to be set)
    aggregated_freq: Dict[str, List[float]] = {}
    
    # Get the number of queries (inferred from the first value of freq)
    first_key = list(freq.keys())[0]
    num_queries = len(freq[first_key])

    # If the interval is too short to split, use the original frequencies as is (fallback)
    if duration < 3:
        for t_idx in [node.min_idx, node.median_idx, node.max_idx]:
            ts_name = timesteps[t_idx]
            aggregated_freq[ts_name] = freq[ts_name]
    else:
        # Compute the equal three-way split
        partition_size = duration / 3.0
        
        # Compute the boundary indices of the sub-intervals
        # Sub-interval 1: [start, b1)
        # Sub-interval 2: [b1, b2)
        # Sub-interval 3: [b2, end] (the last one includes end)
        b1 = int(start_idx + partition_size)
        b2 = int(start_idx + partition_size * 2)
        
        # Define the three sub-intervals (start index, end index (exclusive))
        # but the last sub-interval extends to end_idx + 1 (to make it inclusive)
        ranges = [
            (start_idx, b1),      # Mapped to min_idx
            (b1, b2),             # Mapped to median_idx
            (b2, end_idx + 1)     # Mapped to max_idx
        ]
        
        # Target time step indices of the mapping
        target_indices = [node.min_idx, node.median_idx, node.max_idx]
        
        for range_idx, (r_start, r_end) in enumerate(ranges):
            # Initialize the accumulation array
            total_freqs = [0.0] * num_queries
            
            # Sum the frequencies over all time steps in the sub-interval
            # r_end is exclusive, so it can be used directly with range
            for t in range(r_start, r_end):
                # Guard against out-of-range access (just in case)
                if t >= len(timesteps): continue
                
                ts_name = timesteps[t]
                current_freqs = freq[ts_name]
                
                for q in range(num_queries):
                    total_freqs[q] += current_freqs[q]
            
            # Register the aggregated result as the frequency of the representative time step
            # LocalILPOptimizer looks it up with keys such as timesteps[node.min_idx]
            target_ts_name = timesteps[target_indices[range_idx]]
            aggregated_freq[target_ts_name] = total_freqs

    # --- End of change ---

    # Prepare timestep indices for this node
    timestep_indices = [node.min_idx, node.median_idx, node.max_idx]
    
    # Prepare fixed MV constraints based on parent boundaries
    fixed_mvs_by_timestep: Dict[int, Set[int]] = {}

    if inherit_parent_constraints:
        # Left child: fix min to parent's min, max to parent's median
        if is_left_child:
            if parent_min_mvs:
                fixed_mvs_by_timestep[node.min_idx] = parent_min_mvs.copy()
            if parent_max_mvs:
                fixed_mvs_by_timestep[node.max_idx] = parent_max_mvs.copy()

        # Right child: fix min to parent's median, max to parent's max
        if is_right_child:
            if parent_min_mvs:
                fixed_mvs_by_timestep[node.min_idx] = parent_min_mvs.copy()
            if parent_max_mvs:
                fixed_mvs_by_timestep[node.max_idx] = parent_max_mvs.copy()
    
    # Create and solve local ILP
    local_optimizer = LocalILPOptimizer(
        node_list=node_list,
        u_ij=u_ij,
        X=X,
        b_j=b_j,
        B_max=B_max,
        timestep_indices=timestep_indices,
        all_timesteps=timesteps,
        migration_cost=migration_cost,
        query_frequency_by_timestep=aggregated_freq,  # Changed: pass the aggregated frequencies
        fixed_mvs_by_timestep=fixed_mvs_by_timestep,
        candidate_indices=cand_j,
        gurobi_output=gurobi_output,
    )

    result = local_optimizer.optimize()
    
    # Extract selected MVs from optimal solution (for parent-child constraints)
    selected_mvs_optimal: Set[int] = set()
    for t_idx, mvs in result["selected_mvs_by_timestep"].items():
        selected_mvs_optimal.update(mvs)
    
    # Extract pool MVs if available (for pruning)
    pool_mvs = result.get("pool_mvs", set())
    
    # Extract MVs at each timestep for passing to children (from optimal solution)
    min_mvs = result["selected_mvs_by_timestep"].get(node.min_idx, set())
    median_mvs = result["selected_mvs_by_timestep"].get(node.median_idx, set())
    max_mvs = result["selected_mvs_by_timestep"].get(node.max_idx, set())
    
    return {
        "selected_mvs": selected_mvs_optimal,  # Optimal solution for display
        "pool_mvs": pool_mvs,  # Pool MVs for pruning
        "min_mvs": min_mvs,  # For child constraints (optimal only)
        "median_mvs": median_mvs,  # For child constraints (optimal only)
        "max_mvs": max_mvs,  # For child constraints (optimal only)
        "timestep_indices": timestep_indices,
    }

