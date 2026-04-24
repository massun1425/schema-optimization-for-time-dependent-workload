import pandas as pd

print("Loading parquet...")
df = pd.read_parquet('Redbench/data/full_serverless.parquet',
                     columns=['instance_id', 'database_id', 'arrival_timestamp', 'query_type', 'num_joins', 'read_table_ids'])

c53 = df[(df['instance_id'] == 53) & (df['query_type'] == 'select')].copy()
print(f"Cluster 53 select rows: {len(c53)}")

c53['ts'] = pd.to_datetime(c53['arrival_timestamp'])
c53['date'] = c53['ts'].dt.date
c53['hour'] = c53['ts'].dt.hour

# Per database_id x date stats
daily = c53.groupby(['database_id', 'date']).agg(
    queries=('query_type', 'count'),
    active_hours=('hour', 'nunique'),
    avg_joins=('num_joins', 'mean'),
).reset_index()

# 2-day windows
results = []
for db_id, g in daily.groupby('database_id'):
    g = g.sort_values('date').reset_index(drop=True)
    for i in range(len(g) - 1):
        r1, r2 = g.iloc[i], g.iloc[i+1]
        if (r2['date'] - r1['date']).days == 1:
            total_q = int(r1.queries + r2.queries)
            min_h = min(int(r1.active_hours), int(r2.active_hours))
            avg_j = (r1.avg_joins * r1.queries + r2.avg_joins * r2.queries) / total_q
            results.append({
                'database_id': db_id,
                'start': r1['date'],
                'end': r2['date'],
                'queries': total_q,
                'min_hours': min_h,
                'avg_joins': round(avg_j, 2),
            })

res_df = pd.DataFrame(results).sort_values('queries', ascending=False)
print()
print("=== Top 20 2-day windows for Cluster 53 (all database_ids) ===")
print(res_df.head(20).to_string(index=False))
