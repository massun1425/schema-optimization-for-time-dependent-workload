#!/usr/bin/env python3
"""Test if non-leaf nodes have enhanced info after parsing"""

import json
from src.core.query_parser import QueryParser
from config.settings import Settings

# Load a specific query JSON
json_file = "Output/parsed/8b.json"

with open(json_file) as f:
    data = json.load(f)

# Create parser
qp = QueryParser(Settings())

# Convert the JSON
converted_data, deep_list, order_list = qp.convert_json(data, freq=1)

# Process with DFS
for j, subquery in zip(order_list, converted_data):
    result = qp.qm.depth_first_search(subquery, [0, j])

print(f"=== Non-leaf nodes with enhanced info ===")
for node_id, info in qp.qm.non_leaf_nodes_info.items():
    print(f"\n{node_id}:")
    print(f"  Children: {info.children}")
    print(f"  JOIN Conditions: {len(info.join_conditions)}")
    for jc in info.join_conditions:
        print(f"    {jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
    
    if node_id == "non_leaf_157":
        print(f"\n=== Found non_leaf_157! ===")
        print(f"  Operator: {info.operator}")
        print(f"  JOIN Type: {info.join_type}")
        print(f"  Filters: {info.filters}")
