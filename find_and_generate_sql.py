#!/usr/bin/env python3
"""Generate SQL for non_leaf_5 which corresponds to non_leaf_157 in plan"""

import json
from src.core.query_parser import QueryParser
from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
from config.settings import Settings

# Load the query JSON
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

# Check which node has the structure we're looking for
# non_leaf_157 should have: mc, cn, t, ci
target_tables = {'mc', 'cn', 't', 'ci'}

print("=== Looking for node with tables: mc, cn, t, ci ===\n")

for node_id, info in qp.qm.non_leaf_nodes_info.items():
    # Get all tables in this node
    def get_all_tables(nid):
        tables = set()
        if nid.startswith('leaf_'):
            if nid in qp.qm.leaf_nodes_map_r:
                _, table, alias, _ = qp.qm.leaf_nodes_map_r[nid]
                tables.add(alias)
        elif nid.startswith('non_leaf_'):
            if nid in qp.qm.non_leaf_nodes_info:
                for child in qp.qm.non_leaf_nodes_info[nid].children:
                    tables.update(get_all_tables(child))
        return tables
    
    node_tables = get_all_tables(node_id)
    
    if target_tables.issubset(node_tables):
        print(f"Found: {node_id}")
        print(f"  Tables: {node_tables}")
        print(f"  Children: {info.children}")
        print(f"  JOIN Conditions ({len(info.join_conditions)}):")
        for jc in info.join_conditions:
            print(f"    {jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
        
        # Generate SQL
        gen = EnhancedMVGenerator(qp.qm)
        sql = gen.generate_mv_sql(node_id)
        
        print(f"\n=== Generated SQL for {node_id} ===")
        print(sql)
        print("\n" + "="*60 + "\n")
