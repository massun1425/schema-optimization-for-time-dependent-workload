import json
import os
import glob
import shutil

dir53 = 'experiments/small_test_ver2/01_queries/cluster_53_join'
dir55 = 'experiments/small_test_ver2/01_queries/cluster_55_join'
dir_out = 'experiments/small_test_ver2/01_queries/cluster_55_53_combined'

print("1. SQLファイルをリセット中...")
for f in glob.glob(os.path.join(dir_out, '*.sql')):
    os.remove(f)

print("2. cluster_53_join と cluster_55_join からSQLファイルをコピー中...")
for d in [dir53, dir55]:
    for f in glob.glob(os.path.join(d, '*.sql')):
        target = os.path.join(dir_out, os.path.basename(f))
        if not os.path.exists(target):
            shutil.copy(f, target)

def combine_freq(f1, f2, fout):
    if not os.path.exists(f1) or not os.path.exists(f2):
        return
    with open(f1) as f: d1 = json.load(f)
    with open(f2) as f: d2 = json.load(f)
    
    combined = {}
    keys = set(d1['queries'].keys()).union(set(d2['queries'].keys()))
    
    sample1 = next(iter(d1['queries'].values()))
    l_len = len(sample1)
    
    for k in keys:
        l1 = d1['queries'].get(k, [0]*l_len)
        l2 = d2['queries'].get(k, [0]*l_len)
        combined[k] = [a + b for a, b in zip(l1, l2)]
    
    out_data = {
        "description": "Generated from workload.csv (cluster 53 and 55 combined)",
        "note": "queries format: filename -> frequency list per timestep",
        "queries": combined
    }
    with open(fout, 'w') as f:
        json.dump(out_data, f, indent=2)

print("3. JSONファイルを合成中...")
combine_freq(
    os.path.join(dir53, 'frequency_time_dependent_2h.json'),
    os.path.join(dir55, 'frequency_time_dependent_2h.json'),
    os.path.join(dir_out, 'frequency_time_dependent_2h.json')
)
combine_freq(
    os.path.join(dir53, 'frequency_time_dependent_2h_x2.json'),
    os.path.join(dir55, 'frequency_time_dependent_2h_x2.json'),
    os.path.join(dir_out, 'frequency_time_dependent_2h_x2.json')
)

sql_count = len(glob.glob(os.path.join(dir_out, '*.sql')))
with open(os.path.join(dir_out, 'frequency_time_dependent_2h_x2.json')) as f:
    json_count = len(json.load(f)['queries'])

print(f"完了しました！\nフォルダ内のSQLファイル数: {sql_count}\nJSON内のクエリ数: {json_count}")
