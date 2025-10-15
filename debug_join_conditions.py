#!/usr/bin/env python3
"""Debug script to check JOIN conditions extraction"""

import json
from src.core.query_parser import QueryParser
from src.core.query_manager import QueryManager

# Load the problematic query
with open("Output/parsed/8b.json") as f:
    data = json.load(f)

# Create parser and manager
qp = QueryParser()
qm = QueryManager()

# Find non_leaf_157 in the plan
def find_node(node, target_id):
    if node.get("node_id") == target_id:
        return node
    if "Plans" in node:
        for child in node["Plans"]:
            result = find_node(child, target_id)
            if result:
                return result
    return None

# Find the node
target_node = find_node(data[0]["Plan"], "non_leaf_157")

if target_node:
    print("=== non_leaf_157 Node ===")
    print(f"Node Type: {target_node.get('Node Type')}")
    print(f"Join Filter: {target_node.get('Join Filter')}")
    print()
    
    # Extract join conditions
    join_conditions = qp.extract_join_conditions(target_node)
    
    print(f"=== Extracted JOIN Conditions ({len(join_conditions)}) ===")
    for jc in join_conditions:
        print(f"  {jc.condition_type}: {jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
        print(f"    Original: {jc.original_text}")
    print()
    
    # Check child nodes
    if "Plans" in target_node:
        print(f"=== Child Nodes ({len(target_node['Plans'])}) ===")
        for i, child in enumerate(target_node["Plans"]):
            print(f"Child {i}: {child.get('node_id')} ({child.get('Node Type')})")
            if "Index Cond" in child:
                print(f"  Index Cond: {child['Index Cond']}")
            if "Join Filter" in child:
                print(f"  Join Filter: {child['Join Filter']}")
            
            # Extract from child
            child_jcs = qp.extract_join_conditions(child)
            if child_jcs:
                print(f"  Extracted conditions:")
                for jc in child_jcs:
                    print(f"    {jc.condition_type}: {jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
else:
    print("Node non_leaf_157 not found!")
