import os
import time

ILP_bigsubs = False
ILP_normal = False
ILP_utility_capacity_based = False
ILP_utility_based = False
ILP_frequency_based = False

#ilp_types =  ["normal", "bigsubs", "utility_capacity", "utility", "frequency"]

ilp_types =  ["bigsubs"]

# initalize csv fore each ilp
os.system(f"python compare_bata.py")

for ilp in ilp_types:
    # clear up mv files
    os.system("rm -f Output/query_rewrite/mv/*") # to clean up extra mv

    print(ilp)

    # Materialized view sql scripts creation and rewrites queries with new mv
    os.system(f"python re_sql_exe.py {ilp} > Output/mv_create/{ilp}.out")
    # Run Materialized view sql scripts
    print("Creating MVs")
    os.system(f"bash run_mv.sh > Output/run_mv/{ilp}.out")
    # sets up workloads with new rewritten queries
    print("Setting up Workloads")
    os.system(f"python setup_rewritten.py {ilp}")

    #setup redbench
    os.chdir("dataset/redbench")
    #run redbench
    os.system("python run.py") # might have to test this one out
    # go back to original work directory for the next ilp
    os.chdir("../..")