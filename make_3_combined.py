import json
import os
import glob

dirs = [
    'experiments/small_test_ver2/01_queries/cluster_53_join',
    'experiments/small_test_ver2/01_queries/cluster_55_join',
    'experiments/small_test_ver2/01_queries/cluster_55_join_12_14'
]

out_dir = 'experiments/small_test_ver2/01_queries/cluster_53_55_12_14_combined'
os.makedirs(out_dir, exist_ok=True)

def combine_3_freq(bases_dirs, filename, fout):
    combined = {}
    keys = set()
    dicts = []
    
    for d in bases_dirs:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            with open(p) as f:
                d_json = json.load(f)
                dicts.append(d_json)
                keys.update(d_json['queries'].keys())
                
    if not dicts:
        return None
        
    sample = next(iter(dicts[0]['queries'].values()))
    l_len = len(sample)
    
    for k in keys:
        arrs = []
        for d_json in dicts:
            arrs.append(d_json['queries'].get(k, [0]*l_len))
        
        combined[k] = [sum(x) for x in zip(*arrs)]
        
    out_data = {
        "description": "Generated from combined 3 clusters",
        "note": "queries format: filename -> frequency list per timestep",
        "queries": combined
    }
    with open(fout, 'w') as f:
        json.dump(out_data, f, indent=2)
    return keys

print("1. 3つの頻度ファイルを合成中...")
keys_1 = combine_3_freq(dirs, 'frequency_time_dependent_2h.json', os.path.join(out_dir, 'frequency_time_dependent_2h.json'))
keys_2 = combine_3_freq(dirs, 'frequency_time_dependent_2h_x2.json', os.path.join(out_dir, 'frequency_time_dependent_2h_x2.json'))

print("2. フォルダ内のSQLファイルとの一致確認...")
keys = keys_1 if keys_1 else set()
sql_files = set([os.path.basename(f) for f in glob.glob(os.path.join(out_dir, '*.sql')) if not os.path.basename(f).startswith('frequency_')])

only_in_json = keys - sql_files
only_in_dir = sql_files - keys

print(f'JSON内のクエリ数: {len(keys)}')
print(f'フォルダ内のSQLファイル数: {len(sql_files)}')

if not only_in_json and not only_in_dir:
    print('クエリは完全に一致しています！追加や削除は必要ありません。')
else:
    print('【不一致が発生しています】（※追加・削除は行っていません）')
    if only_in_json:
        print(f' -> JSONにのみ存在するクエリ数: {len(only_in_json)} (SQLファイルが不足しています)')
    if only_in_dir:
        print(f' -> フォルダにのみ存在するSQLファイル数: {len(only_in_dir)} (JSONには記録されていません)')

