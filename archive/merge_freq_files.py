import json
import os

def merge_freq_files(files, out_path):
    merged_queries = {}
    timesteps = 24
    for file_path in files:
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            continue
        with open(file_path, 'r') as f:
            data = json.load(f)
            for q, freqs in data['queries'].items():
                if q not in merged_queries:
                    merged_queries[q] = [0] * timesteps
                for i in range(min(timesteps, len(freqs))):
                    merged_queries[q][i] += freqs[i]
    
    out_dir = os.path.dirname(out_path)
    os.makedirs(out_dir, exist_ok=True)
    
    res = {
        "description": f"Merged from {len(files)} frequency files (sum of identical queries)",
        "note": "queries format: filename -> frequency list per timestep",
        "queries": dict(sorted(merged_queries.items()))
    }
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(f"Created: {out_path} with {len(merged_queries)} queries.")

files_1x = [
    'experiments/small_test_ver2/01_queries/cluster_53_join/frequency_time_dependent_2h.json',
    'experiments/small_test_ver2/01_queries/cluster_55_join/frequency_time_dependent_2h.json',
    'experiments/small_test_ver2/01_queries/cluster_55_join_12_14/frequency_time_dependent_2h.json'
]
out_1x = 'experiments/small_test_ver2/01_queries/cluster_55_53_combined/frequency_time_dependent_2h.json'
merge_freq_files(files_1x, out_1x)

files_2x = [
    'experiments/small_test_ver2/01_queries/cluster_53_join/frequency_time_dependent_2h_x2.json',
    'experiments/small_test_ver2/01_queries/cluster_55_join/frequency_time_dependent_2h_x2.json',
    'experiments/small_test_ver2/01_queries/cluster_55_join_12_14/frequency_time_dependent_2h_x2.json'
]
out_2x = 'experiments/small_test_ver2/01_queries/cluster_55_53_combined/frequency_time_dependent_2h_x2.json'
merge_freq_files(files_2x, out_2x)
