import json
import os

path_join2 = 'experiments/small_test_ver2/01_queries/cluster_55_join_2/frequency_time_dependent.json'
path_03 = 'experiments/small_test_ver2/01_queries/cluster_55_03/frequency_time_dependent.json'

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

qjoin2 = load_freq(path_join2, "cluster_55_join_2")
q03 = load_freq(path_03, "cluster_55_03")

keysjoin2 = set(qjoin2.keys())
keys03 = set(q03.keys())

common = keysjoin2 & keys03
onlyjoin2 = keysjoin2 - keys03
only03 = keys03 - keysjoin2

print("=== 比較 (Comparison) ===")
print(f"  共通クエリ (Common): {len(common)}")
print(f"  cluster_55_join_2 のみ: {len(onlyjoin2)}")
print(f"  cluster_55_03 のみ: {len(only03)}")
