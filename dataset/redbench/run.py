import os
import sys
from src.utils import *
from src.redbench import WORKLOADS_DIR # can be changes in src/redbench.py
from src.imdb import setup_imdb
from prettytable import PrettyTable
from datetime import timedelta
import time
import argparse

# Change depending on computer or OS
DEFAULT_PSQL = os.path.expanduser("/usr/bin/psql")

def parse_args():
    # Parse the arguments
    parser = argparse.ArgumentParser(description="Run Redbench.")
    parser.add_argument(
        "psql",
        type=str,
        nargs="?",
        default=DEFAULT_PSQL,
        help=f"psql binary (default: {DEFAULT_PSQL})."
    )
    parser.add_argument("-v", "--version", action="version", version="v0.1.0")
    args = parser.parse_args()

    # Check whether the binary is available.
    print(os.path.isfile(args.psql))
    if not os.path.isfile(args.psql):
        print(f"Couldn't find {args.psql}. Please install psql and try again.")
        sys.exit(-1)

    return args

def run_sql_cmd(db_cli, db_file, sql_file):
    # set the pgpass.conf to avoid the password prompt
    os.system(f"{db_cli} -h localhost -p 5432 -U  postgres -d {db_file} < {sql_file} > redbench.log")

# Run Redbench
def main(db_cli):
    # Download and setup the IMDb database and its benchmarks JOB and CEB
    setup_imdb(db_cli)

    # Show the psql version
    db_version = os.popen(f"{db_cli}  --version").read().strip()
    #assert db_version is not None, "Something went wrong when extracting the version of your psql binary."
    log(f"Running Redbench on {db_version}")

    exec_times = dict()
    # Iterate over the query repetition buckets
    for subdir in sorted(get_sub_directories(WORKLOADS_DIR)):
        # TODO only do the JOB queries // I think that means i need to change the workloads DIR
        bucket_name = os.path.basename(subdir)
        log(f"Running Redbench bucket {bucket_name}..")
        start_time = time.perf_counter_ns()
        # Iterate over the 3 different variability workloads for this bucket
        for filename in os.listdir(subdir):
            if not filename.endswith(".sql"):
                continue
            filepath = os.path.join(subdir, filename)

            # And run.
            run_sql_cmd(db_cli, 'imdbload', filepath)
        exec_times[bucket_name] = (time.perf_counter_ns() - start_time) / 1e9

    # Prepare and print the results table
    results_table = PrettyTable()
    results_table.field_names = ["Query repetition bucket", "Total execution time"]
    for bucket_name, exec_time in exec_times.items():
        results_table.add_row([bucket_name, str(timedelta(seconds=exec_time))])
    print(results_table)

# And run
if __name__ == "__main__":
    main(parse_args().psql)