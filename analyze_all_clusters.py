import pandas as pd

print("Loading parquet...")
df = pd.read_parquet('Redbench/data/full_serverless.parquet',
                     columns=['instance_id', 'database_id', 'arrival_timestamp', 'query_type', 'num_joins', 'read_table_ids'])

sel = df[df['query_type'] == 'select'].copy()
print(f"Total select rows: {len(sel)}")

sel['ts'] = pd.to_datetime(sel['arrival_timestamp'])
sel['date'] = sel['ts'].dt.date
sel['hour'] = sel['ts'].dt.hour

def avg_scanset(s):
    def count_tables(x):
        if pd.isna(x) or str(x).strip() == '':
            return 0
        return len(set(str(x).split(',')))
    return s.apply(count_tables).mean()

# Per (instance_id, database_id, date)
daily = sel.groupby(['instance_id', 'database_id', 'date']).agg(
    queries=('query_type', 'count'),
    active_hours=('hour', 'nunique'),
    avg_joins=('num_joins', 'mean'),
    avg_scanset=('read_table_ids', avg_scanset),
).reset_index()

# 2-day consecutive windows
results = []
for (inst_id, db_id), g in daily.groupby(['instance_id', 'database_id']):
    g = g.sort_values('date').reset_index(drop=True)
    for i in range(len(g) - 1):
        r1, r2 = g.iloc[i], g.iloc[i+1]
        if (r2['date'] - r1['date']).days == 1:
            total_q = int(r1.queries + r2.queries)
            min_h = min(int(r1.active_hours), int(r2.active_hours))
            avg_j = (r1.avg_joins * r1.queries + r2.avg_joins * r2.queries) / total_q
            avg_s = (r1.avg_scanset * r1.queries + r2.avg_scanset * r2.queries) / total_q
            results.append({
                'instance_id': inst_id,
                'database_id': db_id,
                'start': r1['date'],
                'end': r2['date'],
                'queries': total_q,
                'min_hours': min_h,
                'avg_joins': round(avg_j, 2),
                'avg_scanset': round(avg_s, 2),
            })

res_df = pd.DataFrame(results)

# Cluster 55 for reference
ref = res_df[res_df['instance_id'] == 55].nlargest(1, 'queries').iloc[0]
print(f"\n[Reference] Cluster 55 best: {ref.queries} queries, avg_joins={ref.avg_joins}, avg_scanset={ref.avg_scanset}")

print("\n=== Top 30 windows: sorted by avg_joins desc (queries >= 200, avg_scanset >= 1.0, excluding cluster 55) ===")
filtered = res_df[(res_df['instance_id'] != 55) & (res_df['queries'] >= 200) & (res_df['avg_scanset'] >= 1.0)]
top = filtered.sort_values(['avg_joins', 'queries'], ascending=False).head(30)
print(top[['instance_id','database_id','start','end','queries','min_hours','avg_joins','avg_scanset']].to_string(index=False))

print("\n=== Top 30 windows: sorted by queries desc (avg_joins >= 5.0, avg_scanset >= 1.0, excluding cluster 55) ===")
filtered2 = res_df[(res_df['instance_id'] != 55) & (res_df['avg_joins'] >= 5.0) & (res_df['avg_scanset'] >= 1.0)]
top2 = filtered2.sort_values('queries', ascending=False).head(30)
print(top2[['instance_id','database_id','start','end','queries','min_hours','avg_joins','avg_scanset']].to_string(index=False))
