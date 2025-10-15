#!/usr/bin/env python3
"""Debug SQL generation for non_leaf_157"""

from src.core.query_parser import QueryParser
from src.core.query_manager import QueryManager
from src.rewrite.enhanced_mv_generator import EnhancedMVGenerator
from config.settings import Settings

# Parse the query
settings = Settings()
qp = QueryParser(settings)

# Parse the workload  
# Use the directory where JSON query plans are stored
qp.query_parse(
    q_num=1,
    path="Output/bigsubs/json",  # Changed from parsed to bigsubs/json
    insert_query=1000
)

qm = qp.qm

# Check if non_leaf_157 has enhanced info
node_id = "non_leaf_157"

print(f"=== QueryManager Info for {node_id} ===")

if node_id in qm.non_leaf_nodes_info:
    node_info = qm.non_leaf_nodes_info[node_id]
    print(f"Children: {node_info.children}")
    print(f"JOIN Type: {node_info.join_type}")
    print(f"JOIN Conditions ({len(node_info.join_conditions)}):")
    for jc in node_info.join_conditions:
        print(f"  {jc.left_table}.{jc.left_column} {jc.operator} {jc.right_table}.{jc.right_column}")
    print(f"Filters: {node_info.filters}")
else:
    print(f"No enhanced info for {node_id}")

print()

# Generate SQL
gen = EnhancedMVGenerator(qm)
sql = gen.generate_mv_sql(node_id)

print(f"=== Generated SQL ===")
print(sql)
