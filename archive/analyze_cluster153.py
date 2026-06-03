import pandas as pd

df = pd.read_parquet('Redbench/data/full_serverless.parquet',
                     columns=['instance_id', 'database_id', 'arrival_timestamp', 'query_type', 'num_joins', 'read_table_ids'])

c153 = df[(df['instance_id'] == 153) & (df['query_type'] == 'select')].copy()
c153['ts'] = pd.to_datetime(c153['arrival_timestamp'])
c153['date'] = c153['ts'].dt.date
c153['hour'] = c153['ts'].dt.hour

def avg_scanset(s):
    def count_tables(x):
        if pd.isna(x) or str(x).strip() == '': return 0
        return len(set(str(x).split(',')))
    return s.apply(count_tables).mean()

print(f"=== Cluster 153 overall ===")
print(f"Total select queries: {len(c153)}")
print(f"Date range: {c153['date'].min()} to {c153['date'].max()}")
print(f"database_ids: {sorted(c153['database_id'].unique())}")

# Per database_id summary
print("\n=== Per database_id summary ===")
for db_id, g in c153.groupby('database_id'):
    print(f"  database_id={db_id}: queries={len(g)}, dates={g['date'].min()}~{g['date'].max()}, avg_joins={g['num_joins'].mean():.2f}, avg_scanset={avg_scanset(g['read_table_ids']):.2f}")

# 2-day windows per database_id
daily = c153.groupby(['database_id', 'date']).agg(
    queries=('query_type', 'count'),
    active_hours=('hour', 'nunique'),
    avg_joins=('num_joins', 'mean'),
    avg_scanset=('read_table_ids', avg_scanset),
).reset_index()

results = []
for db_id, g in daily.groupby('database_id'):
    g = g.sort_values('date').reset_index(drop=True)
    for i in range(len(g) - 1):
        r1, r2 = g.iloc[i], g.iloc[i+1]
        if (r2['date'] - r1['date']).days == 1:
            total_q = int(r1.queries + r2.queries)
            min_h = min(int(r1.active_hours), int(r2.active_hours))
            avg_j = (r1.avg_joins * r1.queries + r2.avg_joins * r2.queries) / total_q
            avg_s = (r1.avg_scanset * r1.queries + r2.avg_scanset * r2.queries) / total_q
            results.append({'database_id': db_id, 'start': r1['date'], 'end': r2['date'],
                            'queries': total_q, 'min_hours': min_h,
                            'avg_joins': round(avg_j, 2), 'avg_scanset': round(avg_s, 2)})

res_df = pd.DataFrame(results).sort_values('queries', ascending=False)
print("\n=== Top 20 2-day windows for Cluster 153 ===")
print(res_df.head(20).to_string(index=False))
