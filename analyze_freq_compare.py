import json

def load_freq(path):
    with open(path, 'r') as f:
        data = json.load(f)
    queries = data.get('queries', {})
    return {q: sum(counts) for q, counts in queries.items()}

p55 = 'experiments/small_test_ver2/01_queries/cluster_55_join/frequency_time_dependent_join.json'
p53 = 'experiments/small_test_ver2/01_queries/cluster_53_join/frequency_time_dependent_join.json'

q55 = load_freq(p55)
q53 = load_freq(p53)

keys55 = set(q55.keys())
keys53 = set(q53.keys())
common = keys55 & keys53
only55 = keys55 - keys53
only53 = keys53 - keys55

total55 = sum(q55.values())
total53 = sum(q53.values())

multi_only55 = sum(1 for k in only55 if q55[k] > 1)
multi_only53 = sum(1 for k in only53 if q53[k] > 1)

print("=== cluster_55_join (2024-05-25~26) ===")
print(f"  クエリ種類数: {len(q55)}")
print(f"  総実行回数: {total55}")
print()
print("=== cluster_53_join ===")
print(f"  クエリ種類数: {len(q53)}")
print(f"  総実行回数: {total53}")
print()
print("=== 比較 ===")
print(f"  共通クエリ: {len(common)}")
print(f"  cluster_55_join のみ: {len(only55)}")
print(f"    うち複数回実行: {multi_only55}")
print(f"  cluster_53_join のみ: {len(only53)}")
print(f"    うち複数回実行: {multi_only53}")
