"""Test script to verify neighbor search functionality."""

import json
from pathlib import Path
from src.core.query_manager import QueryManager
from src.optimization.frequency import FrequencyOptimizer
from config.settings import Settings

# Load settings
settings = Settings()

# Load query manager data
qm_path = Path("Output/frequency/query_parsing/query_manager.json")
if not qm_path.exists():
    print("Error: query_manager.json not found")
    exit(1)

with open(qm_path, "r") as f:
    qm_data = json.load(f)

qm = QueryManager.from_dict(qm_data)

# Load optimization input data
opt_input_path = Path("Output/frequency/query_parsing/optimization_input.json")
if not opt_input_path.exists():
    print("Error: optimization_input.json not found")
    exit(1)

with open(opt_input_path, "r") as f:
    opt_data = json.load(f)

# Extract parameters
s_num = opt_data["s_num"]
node_list = opt_data["node_list"]
m_cost = opt_data["m_cost"]
b_j = opt_data["b_j"]
u_ij = opt_data["u_ij"]
X = opt_data["X"]
q_s_list = opt_data["q_s_list"]
position_node_id = {tuple(k): v for k, v in opt_data["position_node_id"].items()}
deeplist = opt_data["deeplist"]

# Set storage budget
B_max = settings.storage_budget_mb * 1024 * 1024  # Convert MB to bytes

# Create optimizer
optimizer = FrequencyOptimizer(
    qm=qm,
    s_num=s_num,
    m_cost=m_cost,
    node_list=node_list,
    B_max=B_max,
    b_j=b_j,
    u_ij=u_ij,
    X=X,
    q_s_list=q_s_list,
    position_node_id=position_node_id,
    deeplist=deeplist,
    settings=settings,
)

print("Testing neighbor search...")
print(f"Total nodes: {len(node_list)}")
print(f"Storage budget: {B_max / (1024*1024):.2f} MB")

# Initialize greedy
z_j_initial = optimizer.initialize_greedy()
initial_count = sum(z_j_initial)
print(f"\nInitial greedy selection: {initial_count} MVs")
print(f"Initial storage used: {sum(b_j[j] * z_j_initial[j] for j in range(len(z_j_initial))) / (1024*1024):.2f} MB")

# Perform neighbor search
z_j_neighbor = optimizer.neighbor_search(z_j_initial.copy())
neighbor_count = sum(z_j_neighbor)
print(f"\nAfter neighbor search: {neighbor_count} MVs")
print(f"Storage used: {sum(b_j[j] * z_j_neighbor[j] for j in range(len(z_j_neighbor))) / (1024*1024):.2f} MB")
print(f"Added {neighbor_count - initial_count} new MVs through neighbor search")

# Check if position_node_id and deeplist are populated
print(f"\nposition_node_id entries: {len(position_node_id)}")
print(f"deeplist queries: {len(deeplist)}")

if len(deeplist) > 0:
    print(f"Sample deeplist[0]: {deeplist[0][:10] if len(deeplist[0]) > 10 else deeplist[0]}")

# Check a few examples
print("\nChecking neighbor search details:")
for i, selected in enumerate(z_j_initial[:10]):
    if selected == 1:
        node_id = node_list[i]
        positions = qm.subquery_positions.get(node_id, [])
        print(f"\nNode {i}: {node_id}")
        print(f"  Appears in {len(positions)} positions: {positions[:3]}")
        
        # Try to find parents
        for query_id, position in positions[:2]:
            parent_pos = optimizer._find_parent(query_id, position)
            if parent_pos:
                print(f"    Parent of ({query_id}, {position}): {parent_pos}")
                if parent_pos in position_node_id:
                    parent_node = position_node_id[parent_pos]
                    print(f"      -> {parent_node}")
            else:
                print(f"    ({query_id}, {position}) has no parent (is root)")

print("\nNeighbor search test complete!")
