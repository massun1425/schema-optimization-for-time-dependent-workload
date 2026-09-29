"""Shared pytest configuration.

Tests that solve ILPs are marked with @pytest.mark.gurobi. They are skipped when no valid
Gurobi license is available, e.g. in CI after the size-limited license bundled with the
gurobipy package has expired. Tests that do not use Gurobi always run.
"""

import pytest


def _gurobi_available() -> bool:
    try:
        import gurobipy as gp

        env = gp.Env(empty=True)
        env.setParam("OutputFlag", 0)
        env.start()  # checks the license
        env.dispose()
        return True
    except Exception:
        return False


def pytest_collection_modifyitems(config, items):
    if not any("gurobi" in item.keywords for item in items) or _gurobi_available():
        return
    skip = pytest.mark.skip(reason="no valid Gurobi license (e.g. the license bundled with gurobipy expired)")
    for item in items:
        if "gurobi" in item.keywords:
            item.add_marker(skip)
