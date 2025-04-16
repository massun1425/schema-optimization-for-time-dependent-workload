# RS DB SYSTEM

## Installation

Before doing anything make sure to install all the modules (Check [requirements.txt](requirements.txt))

To install the required modules simply execute this command

```
pip install -r requirements.txt
```

## Runnning

python3 run.py

## PostgreSQL server setup

See [JOB](https://github.com/viktorleis/job)

## Setting up gurobi

A gurobi licence is necessary to the project so be sure to go to the gurobi website to set up your licence.

## RedBench

In the [run.py](dataset/redbench/run.py) file change the DEFAULT_PSQL constant

## Method

- step 0 (optionnal): python make_each_sqlfile.py : puts sql files from ceb and job into a folder to rewrite later, only needs to be done once
- step 1: python compare_bata.py
- step 2: python re_sql_exe.py <ilp> : creates mv scripts and rewrites queries
- step 3: bash run_mv.sh : creates mv
- step 4: python setup_rewritten.py : will use the csv and rewritten queries to setup the proper workloads according to frequency
- step 5: python run.py : runs redbench with new workload

