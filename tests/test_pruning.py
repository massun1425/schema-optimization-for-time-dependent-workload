"""Tests of the candidate pruning components: WorkloadSummaryTree, LocalILPOptimizer, CFPruner.

The ILP tests use tiny hand-made instances whose optimum is known analytically, so they
also run with the size-limited Gurobi license that comes with the gurobipy package.

Instance (all MVs have size 1 and the storage budget is 1, i.e. one MV per time step):
    q0 runs at t0 and t1, q1 at the last time steps.
    mv0 gives utility 12 to q0, mv1 gives 10 to q1, mv2 gives only 1 to q0 (dominated by mv0).
    Creating any MV costs 5.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path (tests/ is directly under the repository root)
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.cf_pruner import CFPruner  # noqa: E402
from core.local_ilp_optimizer import LocalILPOptimizer  # noqa: E402
from core.time_dependent_optimizer import TimeDependentOptimizer  # noqa: E402
from core.workload_summary_tree import WorkloadSummaryTree  # noqa: E402

NODE_LIST = ["mv0", "mv1", "mv2"]
U_IJ = [
    [12.0, 0.0, 1.0],   # q0
    [0.0, 10.0, 0.0],   # q1
]
X = [[0] * 3 for _ in range(3)]
B_J = [1.0, 1.0, 1.0]
B_MAX = 1.0
MIGRATION_COST = {0: 5.0, 1: 5.0, 2: 5.0}


def _freq(pattern_q0, pattern_q1):
    return {f"t{t}": [float(a), float(b)] for t, (a, b) in enumerate(zip(pattern_q0, pattern_q1))}


def _selected(z_by_timestep):
    return [{j for j, v in enumerate(z) if v == 1} for z in z_by_timestep]


def test_workload_summary_tree():
    """The tree covers all time steps with valid (min, median, max) indices."""
    for T in [3, 5, 8, 16, 50]:
        tree = WorkloadSummaryTree(T)
        assert tree.root is not None
        assert tree.root.min_idx == 0
        assert tree.root.max_idx == T - 1
        for node in tree.get_all_nodes():
            assert 0 <= node.min_idx < T
            assert 0 <= node.median_idx < T
            assert 0 <= node.max_idx < T
            assert node.min_idx <= node.median_idx <= node.max_idx


@pytest.mark.gurobi
def test_local_ilp_optimizer():
    """LocalILPOptimizer finds the known optimum, with and without fixed MVs."""
    timesteps = ["t0", "t1", "t2"]
    freq = _freq([1, 1, 0], [0, 0, 1])

    def solve(fixed=None):
        return LocalILPOptimizer(
            node_list=NODE_LIST, u_ij=U_IJ, X=X, b_j=B_J, B_max=B_MAX,
            timestep_indices=[0, 1, 2], all_timesteps=timesteps,
            migration_cost=MIGRATION_COST, query_frequency_by_timestep=freq,
            fixed_mvs_by_timestep=fixed,
        ).optimize()

    # Unconstrained: mv0, mv0, mv1  ->  -12 - 12 - 10 + 5 + 5 = -24
    res = solve()
    assert res["selected_mvs_by_timestep"] == {0: {0}, 1: {0}, 2: {1}}
    assert abs(res["objective"] - (-24.0)) < 1e-6

    # mv1 fixed at t0: mv1, mv0, mv1  ->  5 + (-12 + 5) + (-10 + 5) = -7
    res = solve(fixed={0: {1}})
    assert res["selected_mvs_by_timestep"] == {0: {1}, 1: {0}, 2: {1}}
    assert abs(res["objective"] - (-7.0)) < 1e-6


@pytest.mark.gurobi
def test_time_dependent_optimizer_matches_local_ilp():
    """The full time-dependent ILP gives the same optimum as the local ILP on 3 time steps."""
    timesteps = ["t0", "t1", "t2"]
    res = TimeDependentOptimizer(
        node_list=NODE_LIST, u_ij=U_IJ, X=X, b_j=B_J, B_max=B_MAX, timesteps=timesteps,
        migration_cost=MIGRATION_COST, query_frequency_by_timestep=_freq([1, 1, 0], [0, 0, 1]),
    ).optimize()
    assert _selected(res["z_by_timestep"]) == [{0}, {0}, {1}]
    assert abs(res["objective"] - (-24.0)) < 1e-6


@pytest.mark.gurobi
def test_cf_pruner():
    """Pruning drops the dominated candidate and keeps the optimum of the full ILP."""
    timesteps = [f"t{t}" for t in range(5)]
    freq = _freq([1, 1, 1, 0, 0], [0, 0, 0, 1, 1])
    common = dict(node_list=NODE_LIST, u_ij=U_IJ, X=X, b_j=B_J, B_max=B_MAX, timesteps=timesteps,
                  migration_cost=MIGRATION_COST, query_frequency_by_timestep=freq)

    promising = CFPruner(**common).prune_candidates()
    assert promising == {0, 1}  # mv2 is dominated by mv0

    # Parallel pruning yields the same promising set
    assert CFPruner(**common, use_parallel=True, max_workers=2).prune_candidates() == promising

    full = TimeDependentOptimizer(**common).optimize()
    pruned_opt = TimeDependentOptimizer(**common)
    pruned_opt.set_candidates([j for j in pruned_opt.cand_j if j in promising])
    pruned = pruned_opt.optimize()

    # mv0 at t0-t2, mv1 at t3-t4  ->  5 - 36 + 5 - 20 = -46
    expected = [{0}, {0}, {0}, {1}, {1}]
    assert _selected(full["z_by_timestep"]) == expected
    assert _selected(pruned["z_by_timestep"]) == expected
    assert abs(full["objective"] - (-46.0)) < 1e-6
    assert abs(pruned["objective"] - full["objective"]) < 1e-6
