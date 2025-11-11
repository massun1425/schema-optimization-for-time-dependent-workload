"""I/O loaders for time-dependent optimization.

This module provides utilities to load JSON/pickle data required for
time-dependent materialized view optimization with migration costs.
"""

from __future__ import annotations

import ast
import json
import logging
import os
import pickle
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)


def load_qp_inputs(base_dir: str, query_set: str = "job_like") -> dict:
    """
    Load optimization inputs from qp_class.pkl.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)

    Returns:
        Dictionary with keys:
            - s_num: Number of subqueries
            - node_list: List of node IDs
            - b_j: List of storage sizes for each MV candidate
            - u_ij: 2D list of utility (benefit) for query i using MV j
            - X: 2D list (J×J) of inclusion relationships
    """
    # Priority: time_dependent_output/qp_class.pkl (9 queries)
    pkl_path = os.path.join(base_dir, "03_parsed", query_set, "qp_class.pkl")

    if not os.path.exists(pkl_path):
        raise FileNotFoundError(f"qp_class.pkl not found in {pkl_path}")
    
    logger.info(f"Loading qp_class.pkl from {pkl_path}")

    with open(pkl_path, "rb") as pf:
        pkl = pickle.load(pf)
    
    # Extract attributes from pickle
    data = {}
    for k in ("s_num", "node_list", "m_cost", "b_j", "u_ij", "X", "q_s_list"):
        if hasattr(pkl, k):
            data[k] = getattr(pkl, k)
        elif isinstance(pkl, dict) and k in pkl:
            data[k] = pkl[k]

    # Fallback for missing fields
    node_list = data.get("node_list") or []
    J = len(node_list)
    I = len(data.get("u_ij") or []) or len(data.get("q_s_list") or [])

    data.setdefault("s_num", J)
    data.setdefault("b_j", data.get("b_j") or [1] * J)
    data.setdefault("u_ij", data.get("u_ij") or [[0.0] * J for _ in range(I or 1)])
    # X: inclusion matrix (J×J)
    data.setdefault("X", data.get("X") or [[0] * J for _ in range(J)])

    return {
        "s_num": int(data.get("s_num", J)),
        "node_list": node_list,
        "b_j": list(map(float, data.get("b_j", [1] * J))),
        "u_ij": data.get("u_ij"),
        "X": data.get("X"),
    }


def load_timesteps_and_frequencies(base_dir: str, query_set: str = "job_like") -> Tuple[List[str], Dict[str, List[float]]]:
    """
    Extract timesteps and query frequencies from frequency_time_dependent.json.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)

    Returns:
        Tuple of (timestep_names, frequency_dict)
        - timestep_names: List of timestep IDs (e.g., ["morning", "evening"])
        - frequency_dict: Dict mapping timestep ID to list of query frequencies
    """
    freq_path = os.path.join(base_dir, "01_queries", query_set, "frequency_time_dependent.json")
    if not os.path.exists(freq_path):
        logger.warning(f"frequency_time_dependent.json not found in {freq_path}, using defaults")
        return ["t0", "t1"], {"t0": [1.0], "t1": [1.0]}

    with open(freq_path, "r", encoding="utf-8") as f:
        freq_data = json.load(f)

    timestep_data = freq_data.get("timesteps", [])
    if not timestep_data:
        logger.warning("No timesteps found in frequency_time_dependent.json")
        return ["t0", "t1"], {"t0": [1.0], "t1": [1.0]}

    timesteps = []
    frequencies = {}

    for ts_entry in timestep_data:
        time_id = ts_entry.get("time_id")
        if not time_id:
            continue

        timesteps.append(time_id)
        frequencies_dict = ts_entry.get("frequencies", {})
        
        # Sort by query filename (query1.json, query2.json, ...)
        query_files = sorted(
            frequencies_dict.keys(), 
            key=lambda x: int(x.replace("query", "").replace(".json", ""))
        )
        freq_list = [float(frequencies_dict.get(qf, 1.0)) for qf in query_files]
        frequencies[time_id] = freq_list

    return timesteps, frequencies

# 今は使っていない
def load_query_frequency(
    base_dir: str, timesteps: List[str], query_count: int
) -> Dict[str, List[float]]:
    """
    DEPRECATED: Use load_timesteps_and_frequencies instead.
    
    Load query frequency for each timestep from frequency_time_dependent.json.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)
        timesteps: List of timestep names
        query_count: Number of queries (I)

    Returns:
        Dictionary mapping timestep name to list of frequencies (length I)
    """
    logger.warning("load_query_frequency is deprecated, use load_timesteps_and_frequencies")
    timesteps_loaded, frequencies = load_timesteps_and_frequencies(base_dir)
    
    # Ensure correct length for all timesteps
    result = {}
    for t in timesteps:
        if t in frequencies:
            freq_list = frequencies[t]
            if len(freq_list) < query_count:
                freq_list.extend([1.0] * (query_count - len(freq_list)))
            elif len(freq_list) > query_count:
                freq_list = freq_list[:query_count]
            result[t] = freq_list
        else:
            result[t] = [1.0] * query_count
    
    return result


def parse_migration_costs(
    base_dir: str, node_list: List[str], query_set: str = "job_like"
) -> Dict[int, List[Tuple[Tuple[int, ...], float]]]:
    """
    Parse migration_costs.json into recipe format.

    Args:
        base_dir: Base directory (e.g., experiments/small_test_ver2)
        node_list: List of node IDs (from qp_class.pkl) for index mapping
        query_set: Query set name (e.g., "job_like", "explicit_join")

    Returns:
        Dictionary mapping j (MV index) to list of (recipe_tuple, cost)
        where recipe_tuple is a tuple of dependency indices.
    """

    path = os.path.join(base_dir, "04_migration", query_set, "migration_costs.json")

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    idx = {node_id: j for j, node_id in enumerate(node_list)}
    mig: Dict[int, List[Tuple[Tuple[int, ...], float]]] = {}

    for node_id, mapping in raw.items():
        j = idx.get(node_id)
        if j is None:
            logger.debug(f"Node {node_id} not found in node_list, skipping")
            continue

        recipes: List[Tuple[Tuple[int, ...], float]] = []
        for k_str, cost in mapping.items():
            try:
                ids = ast.literal_eval(k_str)
                if not isinstance(ids, list):
                    ids = []
            except Exception:
                ids = []

            dep_indices: List[int] = []
            for dep_node_id in ids:
                dep_j = idx.get(dep_node_id)
                if dep_j is not None:
                    dep_indices.append(dep_j)
                else:
                    logger.debug(f"Dependency {dep_node_id} not found in node_list for {node_id}")

            recipes.append((tuple(sorted(dep_indices)), float(cost)))

        # Add fallback empty recipe (full build) if not present
        if not any(len(r[0]) == 0 for r in recipes):
            logger.warning(f"Node {node_id} has no full-build recipe (empty list), adding with inf cost")
            recipes.append((tuple(), float("inf")))

        mig[j] = recipes

    return mig
