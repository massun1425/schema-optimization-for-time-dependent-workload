import json
import os

path_05 = 'experiments/small_test_ver2/01_queries/cluster_55_05/frequency_time_dependent.json'
path_join = 'experiments/small_test_ver2/01_queries/cluster_55_join/frequency_time_dependent_join.json'

def load_freq(path, name):
    if not os.path.exists(path):
        print(f"Error: {path} not found")
        return {}
    with open(path, 'r') as f:
        data = json.load(f)
    queries = data.get('queries', {})
    
    total = 0
    for q, counts in queries.items():
        if isinstance(counts, list):
            total += sum(counts)
        else:
            total += counts
            
    print(f"=== {name} ===")
    print(f"  クエリ種類数: {len(queries)}")
    print(f"  総実行回数: {total}")
    print()
    return queries

q05 = load_freq(path_05, "cluster_55_05")
qjoin = load_freq(path_join, "cluster_55_join")

keys05 = set(q05.keys())
keysjoin = set(qjoin.keys())

common = keys05 & keysjoin
only05 = keys05 - keysjoin
onlyjoin = keysjoin - keys05

print("=== 比較 (Comparison) ===")
print(f"  共通クエリ (Common): {len(common)}")
print(f"  cluster_55_05 のみ (Only in 05): {len(only05)}")
print(f"  cluster_55_join のみ (Only in join): {len(onlyjoin)}")
