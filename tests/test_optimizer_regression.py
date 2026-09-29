"""Regression test of the optimization pipeline (candidate pruning + time-dependent ILP).

A seeded random instance (12 queries, 15 MV candidates, 6 time steps, with some inclusion
relations) is optimized with and without pruning. The promising MV set, the objective values
and the MVs selected at every time step must match the recorded values in
tests/data/optimizer_regression_expected.json. This detects refactorings that change the
optimization results. The instance is small enough for the size-limited Gurobi license, and
its utilities/costs are non-integral so that the optimum is unique (no tie-breaking).

After an intended change of the optimization, regenerate the expected values with
    python tests/test_optimizer_regression.py --update
"""

import json
import random
import sys
from pathlib import Path

import pytest

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from core.cf_pruner import CFPruner  # noqa: E402
from core.time_dependent_optimizer import TimeDependentOptimizer  # noqa: E402

EXPECTED_FILE = Path(__file__).resolve().parent / "data" / "optimizer_regression_expected.json"
OBJ_TOL = 1e-6


def build_instance(seed=0, n_queries=12, n_mvs=15, n_timesteps=6, mvs_per_query=4):
    rng = random.Random(seed)
    node_list = [f"mv{j}" for j in range(n_mvs)]
    u_ij = [[0.0] * n_mvs for _ in range(n_queries)]
    for i in range(n_queries):
        for j in rng.sample(range(n_mvs), mvs_per_query):
            u_ij[i][j] = round(rng.uniform(1.0, 100.0), 3)
    # X[j][u] = 1 if MV j contains MV u
    X = [[0] * n_mvs for _ in range(n_mvs)]
    for _ in range(8):
        j, u = rng.sample(range(n_mvs), 2)
        X[j][u] = 1
    b_j = [round(rng.uniform(1.0, 10.0), 3) for _ in range(n_mvs)]
    b_max = 15.0
    migration_cost = {j: round(rng.uniform(5.0, 60.0), 3) for j in range(n_mvs)}
    timesteps = [f"t{t}" for t in range(n_timesteps)]
    # Two query groups whose frequencies change in opposite directions over time
    freq = {}
    for t, ts in enumerate(timesteps):
        freq[ts] = [float(max(0, (n_timesteps - 1 - t if i % 2 == 0 else t) + rng.randint(-1, 1)))
                    for i in range(n_queries)]
    return dict(node_list=node_list, u_ij=u_ij, X=X, b_j=b_j, B_max=b_max, timesteps=timesteps,
                migration_cost=migration_cost, query_frequency_by_timestep=freq)


def run_pipeline():
    inst = build_instance()
    names = inst["node_list"]

    promising = CFPruner(**inst).prune_candidates()

    pruned_opt = TimeDependentOptimizer(**inst)
    pruned_opt.set_candidates([j for j in pruned_opt.cand_j if j in promising])
    pruned = pruned_opt.optimize()
    full = TimeDependentOptimizer(**inst).optimize()

    def selected(res):
        return [[names[j] for j, v in enumerate(z) if v == 1] for z in res["z_by_timestep"]]

    return {
        "promising_mvs": [names[j] for j in sorted(promising)],
        "with_pruning": {"objective": pruned["objective"], "selected_mvs": selected(pruned)},
        "without_pruning": {"objective": full["objective"], "selected_mvs": selected(full)},
    }


@pytest.mark.gurobi
def test_optimizer_regression():
    expected = json.loads(EXPECTED_FILE.read_text(encoding="utf-8"))
    actual = run_pipeline()
    assert actual["promising_mvs"] == expected["promising_mvs"]
    for key in ("with_pruning", "without_pruning"):
        assert actual[key]["selected_mvs"] == expected[key]["selected_mvs"], key
        assert abs(actual[key]["objective"] - expected[key]["objective"]) <= OBJ_TOL * max(
            1.0, abs(expected[key]["objective"])), key


if __name__ == "__main__":
    if "--update" in sys.argv:
        EXPECTED_FILE.parent.mkdir(parents=True, exist_ok=True)
        EXPECTED_FILE.write_text(json.dumps(run_pipeline(), indent=2) + "\n", encoding="utf-8")
        print(f"updated: {EXPECTED_FILE}")
    else:
        print(json.dumps(run_pipeline(), indent=2))
