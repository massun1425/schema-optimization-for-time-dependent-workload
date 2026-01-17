#!/usr/bin/env python3
"""Recalculate MV creation costs using pickle-based node relationships.

This script uses the node structure from the parsed query plan (pickle file)
combined with sampled row counts from simple_migration_costs.json to calculate
accurate costs that account for JOIN complexity (especially Nested Loop Joins).

Usage (from project root: /home/masuda/projects/mv-query-optimization):
    # Basic usage (outputs to simple_migration_costs_recalc.json)
    python3 experiments/small_test_ver2/scripts/recalculate_costs.py --query-set job
    
    # Overwrite original file
    python3 experiments/small_test_ver2/scripts/recalculate_costs.py --query-set job --overwrite
"""

import json
import math
import pickle
import argparse
import sys
from pathlib import Path

# Add project root to path for pickle deserialization (pickle contains references to src.*)
PROJECT_ROOT = Path("/home/masuda/projects/mv-query-optimization")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# PostgreSQL Cost Constants (should match postgresql.conf)
BLOCK_SIZE = 8192
SEQ_PAGE_COST = 1.0
RANDOM_PAGE_COST = 4.0
CPU_TUPLE_COST = 0.01
CPU_INDEX_TUPLE_COST = 0.005
CPU_OPERATOR_COST = 0.0025


def load_pickle(pickle_path: Path):
    """Load QueryParser object from pickle file."""
    with open(pickle_path, 'rb') as f:
        return pickle.load(f)


def load_migration_costs(json_path: Path) -> dict:
    """Load migration costs from JSON file."""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_children(qm, node_id: str) -> list:
    """Get children of a node from QueryManager."""
    if node_id in qm.non_leaf_nodes_map_r:
        return list(qm.non_leaf_nodes_map_r[node_id])
    return []


def get_operator(qm, node_id: str) -> str:
    """Get operator type of a node from QueryManager."""
    # First, check if it's a leaf node
    if node_id in qm.leaf_nodes_map_r:
        operator, table, alias, filter_cond = qm.leaf_nodes_map_r[node_id]
        return operator
    
    # For non-leaf nodes, check node_operators mapping
    if node_id in qm.node_operators:
        return qm.node_operators[node_id]
    
    # Fallback to non_leaf_nodes_info
    if hasattr(qm, 'non_leaf_nodes_info') and node_id in qm.non_leaf_nodes_info:
        return qm.non_leaf_nodes_info[node_id].operator
    
    return "Unknown"


def get_rows_from_migration_costs(migration_costs: dict, node_id: str) -> int:
    """Get scaled rows for a node from migration_costs.json."""
    if node_id in migration_costs:
        # Get the "[]" plan key which represents the MV creation cost
        node_data = migration_costs[node_id]
        if "[]" in node_data:
            return node_data["[]"].get("rows", 0)
    return 0


def get_width_from_migration_costs(migration_costs: dict, node_id: str) -> int:
    """Get width for a node from migration_costs.json."""
    if node_id in migration_costs:
        node_data = migration_costs[node_id]
        if "[]" in node_data:
            return node_data["[]"].get("width", 0)
    return 0


def calculate_node_cost(qm, node_id: str, migration_costs: dict, memo: dict) -> tuple:
    """
    Recursively calculate cost for a node using C-Store style model.
    
    Returns:
        Tuple of (total_cost, output_rows)
    """
    # Memoization: avoid recalculating the same node
    if node_id in memo:
        return memo[node_id]
    
    # Get node properties
    operator = get_operator(qm, node_id)
    rows = get_rows_from_migration_costs(migration_costs, node_id)
    width = get_width_from_migration_costs(migration_costs, node_id)
    
    # Fallback to pickle data if not in migration_costs
    if rows == 0 and hasattr(qm, 'subquery_rows') and node_id in qm.subquery_rows:
        rows = qm.subquery_rows[node_id]
    if width == 0 and hasattr(qm, 'subquery_widths') and node_id in qm.subquery_widths:
        width = qm.subquery_widths[node_id]
    
    children = get_children(qm, node_id)
    
    # --- Leaf Node ---
    if not children:
        # Calculate I/O cost
        size_bytes = rows * width
        pages = math.ceil(size_bytes / BLOCK_SIZE) if size_bytes > 0 else 0
        
        if 'Index' in operator and 'Scan' in operator:
            # Index Scan: random I/O
            cost = (rows * RANDOM_PAGE_COST) + (rows * CPU_INDEX_TUPLE_COST)
        else:
            # Seq Scan: sequential I/O
            cost = (pages * SEQ_PAGE_COST) + (rows * CPU_TUPLE_COST)
        
        memo[node_id] = (cost, rows)
        return cost, rows
    
    # --- Non-Leaf Node ---
    # Recursively calculate children costs
    children_costs = []
    children_rows = []
    
    for child_id in children:
        c_cost, c_rows = calculate_node_cost(qm, child_id, migration_costs, memo)
        children_costs.append(c_cost)
        children_rows.append(c_rows)
    
    input_rows_sum = sum(children_rows)
    total_cost = 0.0
    
    # Cost calculation based on operator type
    if operator == 'Nested Loop':
        # children[0]: Outer (駆動表), children[1]: Inner (内部表)
        if len(children_costs) >= 2:
            outer_cost = children_costs[0]
            inner_cost = children_costs[1]
            outer_rows = children_rows[0] if children_rows[0] > 0 else 1
            
            # 内側のノードタイプを確認（pickle経由）
            inner_child_id = children[1] if len(children) >= 2 else None
            inner_type = get_operator(qm, inner_child_id) if inner_child_id else "Unknown"
            
            # ★ Materialize戦略 ★
            
            # ケースA: 内側がインデックススキャン (Index NLJ)
            # 外側の1行ごとに、インデックスを引きに行くコストがかかる
            if 'Index' in inner_type and 'Scan' in inner_type:
                # ランダムアクセス(4.0) + CPU処理(0.005)
                # ※ ここで inner_cost (総コスト) を足さないのがポイント（毎回引くから）
                loop_cost_per_row = RANDOM_PAGE_COST + CPU_INDEX_TUPLE_COST
                
                # Cost = 外側コスト + (外側行数 × 1回のインデックスアクセス)
                total_cost = outer_cost + (outer_rows * loop_cost_per_row) + (rows * CPU_TUPLE_COST)

            # ケースB: それ以外 (Materialized NLJ)
            # 内側を一回全部作ってメモリに置く(inner_cost)。あとは外側行数分、メモリを読むだけ。
            else:
                # メモリ読み出し(0.01) ※非常に軽い
                loop_cost_per_row = CPU_TUPLE_COST
                
                # Cost = 外側コスト + 内側構築コスト(1回分) + (外側行数 × メモリ読み出し)
                total_cost = outer_cost + inner_cost + (outer_rows * loop_cost_per_row) + (rows * CPU_TUPLE_COST)

        else:
            total_cost = sum(children_costs) + (rows * CPU_TUPLE_COST)
    
    elif operator in ('Hash Join', 'Merge Join'):
        # Hash/Merge Join: additive cost
        # Cost = OuterCost + InnerCost + (OuterRows + InnerRows) * OpCost
        my_cost = input_rows_sum * CPU_OPERATOR_COST
        total_cost = sum(children_costs) + my_cost
    
    elif operator == 'Sort':
        # Sort: N log N
        if input_rows_sum > 1:
            my_cost = input_rows_sum * math.log(input_rows_sum, 2) * CPU_OPERATOR_COST
        else:
            my_cost = input_rows_sum * CPU_OPERATOR_COST
        total_cost = sum(children_costs) + my_cost
    
    elif operator == 'Aggregate':
        my_cost = input_rows_sum * CPU_OPERATOR_COST
        total_cost = sum(children_costs) + my_cost
    
    else:
        # Default: sum children costs + pass-through cost
        my_cost = input_rows_sum * CPU_TUPLE_COST
        total_cost = sum(children_costs) + my_cost
    
    memo[node_id] = (total_cost, rows)
    return total_cost, rows


def recalculate_costs(pickle_path: Path, json_input_path: Path, json_output_path: Path):
    """
    Main function to recalculate costs.
    
    Args:
        pickle_path: Path to the pickle file containing QueryParser
        json_input_path: Path to simple_migration_costs.json
        json_output_path: Path to save recalculated costs
    """
    print(f"Loading pickle from: {pickle_path}")
    qp = load_pickle(pickle_path)
    qm = qp.qm  # QueryManager
    
    print(f"Loading migration costs from: {json_input_path}")
    migration_costs = load_migration_costs(json_input_path)
    
    # Memoization dictionary for recursive calculation
    memo = {}
    
    updated_count = 0
    
    # Process all nodes
    all_nodes = list(qm.leaf_nodes_map_r.keys()) + list(qm.non_leaf_nodes_map_r.keys())
    print(f"Processing {len(all_nodes)} nodes...")
    
    for node_id in all_nodes:
        if node_id not in migration_costs:
            continue
        
        # Calculate cost using recursive method
        total_cost, output_rows = calculate_node_cost(qm, node_id, migration_costs, memo)
        
        # Update the JSON data
        if "[]" in migration_costs[node_id]:
            old_cost = migration_costs[node_id]["[]"].get("cost", 0)
            migration_costs[node_id]["[]"]["cost"] = round(total_cost, 2)
            migration_costs[node_id]["[]"]["recalculated"] = True
            migration_costs[node_id]["[]"]["calc_method"] = "pickle_recursive"
            updated_count += 1
    
    print(f"Updated {updated_count} nodes.")
    
    # Save to output file
    json_output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_output_path, 'w', encoding='utf-8') as f:
        json.dump(migration_costs, f, indent=2, ensure_ascii=False)
    
    print(f"Saved recalculated costs to: {json_output_path}")


def main():
    parser = argparse.ArgumentParser(description="Recalculate MV costs using pickle-based node relationships")
    parser.add_argument(
        '--query-set',
        type=str,
        default='job',
        help='Query set to process (default: job)'
    )
    parser.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite input file instead of creating new output file'
    )
    args = parser.parse_args()
    
    # Paths
    base_dir = Path("/home/masuda/projects/mv-query-optimization/experiments/small_test_ver2")
    pickle_path = base_dir / "03_parsed" / args.query_set / "qp_class.pkl"
    json_input_path = base_dir / "04_migration" / args.query_set / "simple_migration_costs.json"
    
    if args.overwrite:
        json_output_path = json_input_path
    else:
        json_output_path = base_dir / "04_migration" / args.query_set / "simple_migration_costs_recalc.json"
    
    # Validate paths
    if not pickle_path.exists():
        print(f"Error: Pickle file not found at {pickle_path}")
        print("Please run Phase 2 (query parsing) first.")
        return 1
    
    if not json_input_path.exists():
        print(f"Error: Migration costs file not found at {json_input_path}")
        print("Please run Phase 5 (migration cost calculation) first.")
        return 1
    
    recalculate_costs(pickle_path, json_input_path, json_output_path)
    return 0


if __name__ == "__main__":
    exit(main())
