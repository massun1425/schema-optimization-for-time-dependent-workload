import json

in_path = 'experiments/small_test_ver2/01_queries/cluster_53_55_12_14_combined/frequency_time_dependent_join.json'
out_path = 'experiments/small_test_ver2/01_queries/cluster_53_55_12_14_combined/frequency_time_dependent_join2.json'

with open(in_path, 'r') as f:
    data = json.load(f)

for q in data['queries']:
    data['queries'][q] = [v * 2 for v in data['queries'][q]]

data['description'] = data.get('description', '') + ' (doubled)'

with open(out_path, 'w') as f:
    json.dump(data, f, indent=2)

print(f'Successfully created {out_path}')
