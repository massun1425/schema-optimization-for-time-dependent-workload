import json
import glob
import os

def check_query_in_folder(cluster, qfile):
    with open(qfile, 'r') as f:
        target_sql = f.read().strip()
    
    # We strip all whitespaces to compare ignoring formatting
    target_clean = "".join(target_sql.split())
    
    base_dir = f"Redbench/output/generated_workloads/imdb/serverless/{cluster}"
    
    for queries_file in glob.glob(f"{base_dir}/**/*.json", recursive=True):
        if not queries_file.endswith("queries.json"): continue
        try:
            with open(queries_file, 'r') as f:
                data = json.load(f)
            
            for q in data.get('queries', []):
                sql = q.get('query', '')
                sql_clean = "".join(sql.split())
                if sql_clean == target_clean:
                    print(f"Found match for {qfile} in: {os.path.dirname(queries_file)}")
                    return
        except Exception as e:
            pass
    print(f"No match found for {qfile} in {cluster}")

check_query_in_folder('cluster_53', 'experiments/small_test_ver2/01_queries/cluster_53_join/10a.sql')
check_query_in_folder('cluster_55', 'experiments/small_test_ver2/01_queries/cluster_55_join/11a.sql')
