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

from experiments.small_test_ver2.core.local_ilp_optimizer import LocalILPOptimizer
from experiments.small_test_ver2.core.workload_summary_tree import (
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
        migration_recipes: Dict[int, List[Tuple[Tuple[int, ...], float]]],
        query_frequency_by_timestep: Dict[str, List[float]],
        gurobi_output: int = 0,
        use_parallel: bool = False,
        max_workers: Optional[int] = 16,
    ):
        """Initialize the CF pruner.
        
        Args:
            node_list: List of node IDs (MV candidates)
            u_ij: Utility matrix [I][J]
            X: Inclusion matrix [J][J]
            b_j: Storage size for each MV candidate
            B_max: Storage budget
            timesteps: List of timestep names
            migration_recipes: Recipe costs for each MV
            query_frequency_by_timestep: Query frequencies for each timestep
            gurobi_output: Gurobi log level (0=off, 1=on)
            use_parallel: Enable parallel processing (default: False)
            max_workers: Maximum number of worker processes (default: CPU count)
        """
        self.node_list = node_list
        self.u_ij = u_ij
        self.X = X
        self.b_j = b_j
        self.B_max = B_max
        self.timesteps = timesteps
        self.recipes = migration_recipes
        self.freq = query_frequency_by_timestep
        self.gurobi_output = gurobi_output
        
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
        candidates = []
        for j in range(self.J):
            has_utility = any(self.u_ij[i][j] > 0 for i in range(self.I))
            if has_utility:
                candidates.append(j)
        
        logger.info(f"Filtered to {len(candidates)} candidates (from {self.J} total nodes)")
        return candidates
    
    def prune_candidates(self) -> Set[int]:
        """Execute the pruning algorithm and return promising MV indices.
        
        This is the main entry point for pruning. It:
        1. Recursively traverses the Workload Summary Tree
        2. Solves local ILPs at each node
        3. Collects all MVs that appear in any solution
        4. Returns the set of promising MV indices
        
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
        if self.use_parallel:
            logger.info(f"Workers: {self.max_workers}")
        logger.info("-" * 70)
        
        # Choose parallel or sequential execution
        if self.use_parallel:
            promising_mvs = self._prune_candidates_parallel()
        else:
            promising_mvs = self._prune_candidates_sequential()
        
        logger.info("-" * 70)
        logger.info(f"CF Pruning Completed!")
        logger.info(f"Promising MVs: {len(promising_mvs)}/{self.J}")
        logger.info(f"Reduction: {100.0 * (1 - len(promising_mvs) / self.J):.1f}%")
        logger.info("=" * 70)
        
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
        
        # Level-by-level processing (BFS approach)
        # Each level: (node, parent_min_mvs, parent_max_mvs, is_left, is_right)
        current_level = [(self.tree.root, set(), set(), False, False)]
        
        while current_level:
            next_level = []
            
            # Process all nodes at this level in parallel
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                # Submit all tasks for this level
                future_to_task = {}
                for node, parent_min, parent_max, is_left, is_right in current_level:
                    future = executor.submit(
                        _solve_node_static,
                        node,
                        parent_min,
                        parent_max,
                        is_left,
                        is_right,
                        self.node_list,
                        self.u_ij,
                        self.X,
                        self.b_j,
                        self.B_max,
                        self.timesteps,
                        self.recipes,
                        self.freq,
                        self.cand_j,
                        self.gurobi_output,
                    )
                    future_to_task[future] = node
                
                # Collect results as they complete
                for future in as_completed(future_to_task):
                    node = future_to_task[future]
                    try:
                        result = future.result()
                        
                        # Update progress
                        self.node_count += 1
                        progress = f"[{self.node_count}/{self.total_nodes}]"
                        
                        # Collect promising MVs
                        before_count = len(promising_mvs)
                        promising_mvs.update(result['selected_mvs'])
                        new_mvs = len(promising_mvs) - before_count
                        
                        logger.info(
                            f"{progress} Processing node: timesteps {result['timestep_indices']}, depth={node.depth}"
                        )
                        logger.info(
                            f"  ✓ Selected {len(result['selected_mvs'])} MVs "
                            f"(+{new_mvs} new, total: {len(promising_mvs)})"
                        )
                        
                        # Prepare children for next level
                        if node.left_child:
                            next_level.append((
                                node.left_child,
                                result['min_mvs'],
                                result['median_mvs'],
                                True,   # is_left_child
                                False,  # is_right_child
                            ))
                        
                        if node.right_child:
                            next_level.append((
                                node.right_child,
                                result['median_mvs'],
                                result['max_mvs'],
                                False,  # is_left_child
                                True,   # is_right_child
                            ))
                    
                    except Exception as e:
                        logger.error(f"Error processing node: {e}")
                        import traceback
                        traceback.print_exc()
            
            current_level = next_level
        
        return promising_mvs
    
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
            
        # Create and solve local ILP
        local_optimizer = LocalILPOptimizer(
            node_list=self.node_list,
            u_ij=self.u_ij,
            X=self.X,
            b_j=self.b_j,
            B_max=self.B_max,
            timestep_indices=timestep_indices,
            all_timesteps=self.timesteps,
            migration_recipes=self.recipes,
            query_frequency_by_timestep=self.freq,
            fixed_mvs_by_timestep=fixed_mvs_by_timestep,
            candidate_indices=self.cand_j,  # ★ 事前計算された候補を渡す
            gurobi_output=self.gurobi_output,
        )
        
        result = local_optimizer.optimize()
        
        # Extract selected MVs from all timesteps in this local solution
        selected_mvs_all_timesteps: Set[int] = set()
        for t_idx, mvs in result["selected_mvs_by_timestep"].items():
            selected_mvs_all_timesteps.update(mvs)
        
        # Add to promising set
        before_count = len(promising_mvs)
        promising_mvs.update(selected_mvs_all_timesteps)
        new_mvs = len(promising_mvs) - before_count
        
        logger.info(
            f"  ✓ Selected {len(selected_mvs_all_timesteps)} MVs "
            f"(+{new_mvs} new, total: {len(promising_mvs)})"
        )
        
        # Extract MVs at each timestep for passing to children
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
        return {
            "total_candidates": self.J,
            "promising_candidates": len(promising_mvs),
            "filtered_out": self.J - len(promising_mvs),
            "retention_rate": len(promising_mvs) / self.J if self.J > 0 else 0.0,
            "reduction_rate": 1.0 - (len(promising_mvs) / self.J) if self.J > 0 else 0.0,
            "promising_mv_names": [self.node_list[j] for j in sorted(promising_mvs)],
        }


# ==============================================================================
# Module-level function for parallel processing
# ==============================================================================
# This must be at module level (not a method) to be pickle-able for 
# ProcessPoolExecutor

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
    recipes: Dict[int, List[Tuple[Tuple[int, ...], float]]],
    freq: Dict[str, List[float]],
    cand_j: List[int],
    gurobi_output: int,
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
        recipes: Migration recipes
        freq: Query frequencies by timestep
        cand_j: Pre-filtered candidate indices
        gurobi_output: Gurobi log level
        
    Returns:
        Dictionary with solution info
    """
    # Prepare timestep indices for this node
    timestep_indices = [node.min_idx, node.median_idx, node.max_idx]
    
    # Prepare fixed MV constraints based on parent boundaries
    fixed_mvs_by_timestep: Dict[int, Set[int]] = {}
    
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
        migration_recipes=recipes,
        query_frequency_by_timestep=freq,
        fixed_mvs_by_timestep=fixed_mvs_by_timestep,
        candidate_indices=cand_j,
        gurobi_output=gurobi_output,
    )
    
    result = local_optimizer.optimize()
    
    # Extract selected MVs from all timesteps in this local solution
    selected_mvs_all_timesteps: Set[int] = set()
    for t_idx, mvs in result["selected_mvs_by_timestep"].items():
        selected_mvs_all_timesteps.update(mvs)
    
    # Extract MVs at each timestep for passing to children
    min_mvs = result["selected_mvs_by_timestep"].get(node.min_idx, set())
    median_mvs = result["selected_mvs_by_timestep"].get(node.median_idx, set())
    max_mvs = result["selected_mvs_by_timestep"].get(node.max_idx, set())
    
    return {
        "selected_mvs": selected_mvs_all_timesteps,
        "min_mvs": min_mvs,
        "median_mvs": median_mvs,
        "max_mvs": max_mvs,
        "timestep_indices": timestep_indices,
    }
