"""Simple test to verify neighbor search logic."""

# Test data
deeplist_sample = [
    [0, 1, 2, 2, 2, 1, 2, 2, 3, 3, 4, 4, 5, 5],  # Query 0
    [0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6],     # Query 1
]

def find_parent(query_id, position, deeplist):
    """Find parent position in query tree."""
    if not deeplist or query_id >= len(deeplist):
        return None
    
    depth_list = deeplist[query_id]
    if position >= len(depth_list) or depth_list[position] == 0:
        # At root
        return None
    
    # Search backward for parent (depth - 1)
    target_depth = depth_list[position] - 1
    for i in range(1, position + 1):
        if position - i >= 0 and depth_list[position - i] == target_depth:
            return (query_id, position - i)
    
    return None

print("Testing _find_parent logic:")
print(f"deeplist[0]: {deeplist_sample[0]}")
print(f"deeplist[1]: {deeplist_sample[1]}")
print()

# Test various positions
test_cases = [
    (0, 0, "Root - should return None"),
    (0, 1, "Depth 1 - parent should be 0"),
    (0, 5, "Depth 1 - parent should be 0"),
    (0, 8, "Depth 3 - parent should be position with depth 2"),
    (0, 12, "Depth 5 - parent should be position with depth 4"),
    (1, 1, "Depth 1 - parent should be 0"),
    (1, 7, "Depth 4 - parent should be position with depth 3"),
]

for query_id, position, description in test_cases:
    parent = find_parent(query_id, position, deeplist_sample)
    current_depth = deeplist_sample[query_id][position]
    print(f"Query {query_id}, Position {position} (depth {current_depth}): {description}")
    if parent:
        parent_depth = deeplist_sample[parent[0]][parent[1]]
        print(f"  -> Parent: {parent} (depth {parent_depth})")
    else:
        print(f"  -> No parent (is root)")
    print()

# Test neighbor search logic
print("\n" + "="*60)
print("Testing neighbor search expansion:")
print("="*60)

# Simulate initial selection
z_j = [1, 0, 0, 1, 0, 0, 0, 0, 1, 0]  # Nodes 0, 3, 8 selected
node_list = [f"node_{i}" for i in range(10)]

# Simulate position_node_id mapping
position_node_id = {
    (0, 0): "node_0",
    (0, 1): "node_1", 
    (0, 5): "node_3",
    (0, 8): "node_8",
    (0, 7): "node_7",
    (0, 2): "node_2",
}

# Simulate qm.subquery_positions
subquery_positions = {
    "node_0": [(0, 0)],           # Root - no parent
    "node_3": [(0, 5)],           # Has parent at (0, 0)
    "node_8": [(0, 8)],           # Has parent (need to find it)
}

print(f"Initial selection: {[i for i, x in enumerate(z_j) if x == 1]}")
print()

new_list_j = []
for i in range(len(z_j)):
    if z_j[i] == 1:
        node_id = node_list[i]
        if node_id not in subquery_positions:
            continue
            
        print(f"Processing {node_id} (index {i}):")
        positions = subquery_positions[node_id]
        
        # Find parents
        uplist = []
        for query_id, position in positions:
            parent_pos = find_parent(query_id, position, deeplist_sample)
            if parent_pos is not None:
                uplist.append(parent_pos)
                print(f"  Found parent for ({query_id}, {position}): {parent_pos}")
        
        # Add parents to new_list_j
        for query_id, position in uplist:
            if (query_id, position) in position_node_id:
                parent_node_id = position_node_id[(query_id, position)]
                try:
                    j = node_list.index(parent_node_id)
                    if j not in new_list_j:
                        new_list_j.append(j)
                        print(f"    -> Adding {parent_node_id} (index {j})")
                except ValueError:
                    print(f"    -> {parent_node_id} not in node_list")

print(f"\nNodes to add: {new_list_j}")
for j in new_list_j:
    z_j[j] = 1

print(f"Final selection: {[i for i, x in enumerate(z_j) if x == 1]}")
print(f"Added {len(new_list_j)} new nodes through neighbor search")
