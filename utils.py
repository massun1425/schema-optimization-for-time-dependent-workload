import os

def get_red_queries(source_path, workloads_dir, get_ceb = False):
    query_paths = []
    query_count = {}
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path+'/'+line.split(",")[0].split('/')[-1]
                    query_path = query_path.split(".")[0] + ".json"
                else:
                    query_path = source_path+'/'+"/".join(line.split(",")[0].split('/')[2:])
                    query_path = query_path.split(".")[0] + ".json"
                if not os.path.exists(query_path):
                    continue
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count


def get_red_queries_sql(source_path, workloads_dir, get_ceb = False):
    query_paths = []
    query_count = {}
    for subdir in sorted([x[0] for x in os.walk(workloads_dir) if x[0] != workloads_dir]):
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            for line in workload:
                if not get_ceb:
                    query_path = source_path+'/'+line.split(",")[0].split('/')[-1]
                else:
                    query_path = source_path+'/'+"/".join(line.split(",")[0].split('/')[2:])
                if not os.path.exists(query_path):
                    continue
                if query_path not in query_paths:
                    query_paths.append(query_path)
                    query_count[query_path] = 1
                else:
                    query_count[query_path] += 1

    return query_paths, query_count