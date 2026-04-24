import csv
from collections import defaultdict

wl_path = 'Redbench/output/generated_workloads/imdb/serverless/cluster_153/database_0/matching_1bfc2312f4053ca7185fe0a6a4648c54/workload.csv'

daily_queries = defaultdict(set)

try:
    with open(wl_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        
        try:
            ts_idx = header.index('arrival_timestamp')
            fp_idx = header.index('feature_fingerprint')
            qt_idx = header.index('query_type')
        except ValueError as e:
            print(f"Header missing required columns: {e}")
            exit(1)
            
        for row in reader:
            if len(row) > max(ts_idx, fp_idx, qt_idx):
                if row[qt_idx] == 'select':
                    # Extract YYYY-MM-DD
                    date_str = row[ts_idx][:10]
                    daily_queries[date_str].add(row[fp_idx])

    dates = sorted(daily_queries.keys())
    
    print('=== Cluster 153 指定期間のクエリ種類数 ===')
    periods_of_interest = [
        ('2024-03-29', '2024-03-30'),
        ('2024-03-30', '2024-03-31'),
        ('2024-03-31', '2024-04-01'),
        ('2024-03-24', '2024-03-25')
    ]
    
    for d1, d2 in periods_of_interest:
        q1 = daily_queries.get(d1, set())
        q2 = daily_queries.get(d2, set())
        union = q1 | q2
        common = q1 & q2
        print(f'{d1} 〜 {d2}: {len(union)} 種類 (共通: {len(common)})')
        
except FileNotFoundError:
    print(f"File not found: {wl_path}")
except Exception as e:
    print(f"Error: {e}")
