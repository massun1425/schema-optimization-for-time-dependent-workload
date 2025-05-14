from dataset.redbench.src.utils import *
from collections import defaultdict
import os
import sys

WORKLOADS_DIR = "Output/RED_WORKLOADS"

ilp_types =  ["normal", "bigsubs", "utility_capacity", "utility", "frequency", "none"]

## Argument handler
if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <ILP type>")
    print("ILP types :")
    for ilp in ilp_types:
        print(f"	{ilp}")
    exit(0)

if sys.argv[1] not in ilp_types:
    print("Non valid argument")
    print("ILP types :")
    for ilp in ilp_types:
        print(f"	{ilp}")
    exit(0)

#INPUT_DIR = "dataset/RED_SQL"

if sys.argv[1] != "none":
    INPUT_DIR = "Output/query_rewrite/re_sql/" + sys.argv[1]
else:
    INPUT_DIR = "dataset/RED_SQL"

# Unpack/ inline the workload queries (convert the csv files to runnable sql files)
def unpack_workloads():
    os.system(f"rm -f {WORKLOADS_DIR}/*/*.sql") # clean up
    log("Unpacking Redbench rewritten workloads.")
    num_queries = defaultdict(int)
    # Iterate over the query repetition groups
    for subdir in sorted(get_sub_directories(WORKLOADS_DIR)):
        group_name = os.path.basename(subdir)   
        # Iterate over the 3 different variability workloads for this group
        for filename in os.listdir(subdir):
            if not filename.endswith(".csv") or filename == "stats.csv":
                continue
            # Read the workload csv
            with open(os.path.join(subdir, filename), "r") as csv_file:
                workload = csv_file.readlines()[1:]
            sql_workload = ""
            # Unpack the queries
            for line in workload:
                num_queries[group_name] += 1
                #query_path = INPUT_DIR+"/"+line.split(",")[0] # can be deleted
                query_path = INPUT_DIR+'/'+line.split(",")[0].split('/')[-1]
                if sys.argv[1] == "none":
                    query_path = INPUT_DIR+'/'+ "/".join(line.split(",")[0].split('/')[2:])
    
                if not os.path.exists(query_path):
                    continue
                with open(query_path, "r") as query_file:
                    query = query_file.read().strip()
                    query += ";" if not query.endswith(";") else ""
                    sql_workload += f"-- {query_path}\n{query}\n\n"
            # Write the unpacked workload to a new sql file
                with open(
                    os.path.join(subdir, filename.replace(".csv", ".sql")), "w"
                ) as sql_workload_file:
                    sql_workload_file.write(sql_workload)
    log("Finished unpacking Redbench rewritten workloads.")
    


if __name__ == "__main__":
    # Setup Workloads with rewritten queries
    unpack_workloads()
