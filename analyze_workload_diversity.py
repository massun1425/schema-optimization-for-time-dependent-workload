import pandas as pd

wl_path = 'Redbench/output/generated_workloads/imdb/serverless/cluster_55/database_0/matching_d5055960d120fe8532606c6e30bf2981/workload.csv'

print("Loading CSV...")
df = pd.read_csv(wl_path, usecols=['arrival_timestamp', 'feature_fingerprint', 'query_type'], low_memory=False)
print(f"Total rows: {len(df)}")

df = df[df['query_type'] == 'select'].copy()
print(f"Select rows: {len(df)}")

df['date'] = pd.to_datetime(df['arrival_timestamp'], format='ISO8601').dt.date

# Get unique query fingerprints per date
daily_queries = df.groupby('date')['feature_fingerprint'].apply(set).to_dict()
dates = sorted(daily_queries.keys())

print(f'Total dates: {len(dates)}')
print(f'Date range: {dates[0]} to {dates[-1]}')

# Find consecutive 2-day windows with maximum query diversity
results = []
for i in range(len(dates) - 1):
    d1, d2 = dates[i], dates[i+1]
    # Only consecutive days
    if (d2 - d1).days != 1:
        continue
    q1 = daily_queries[d1]
    q2 = daily_queries[d2]
    union = q1 | q2
    results.append({
        'start': d1,
        'end': d2,
        'unique_queries': len(union),
        'day1_queries': len(q1),
        'day2_queries': len(q2),
        'common': len(q1 & q2),
        'only_day1': len(q1 - q2),
        'only_day2': len(q2 - q1),
    })

res_df = pd.DataFrame(results).sort_values('unique_queries', ascending=False)
print()
print('=== Top 15 consecutive 2-day windows by unique query types ===')
print(res_df.head(15).to_string(index=False))
