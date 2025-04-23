# RS DB SYSTEM

## Installation

Before doing anything make sure to install all the modules (Check [requirements.txt](requirements.txt))

To install the required modules simply execute this command

```
pip install -r requirements.txt
```

## PostgreSQL server setup

See [JOB](https://github.com/viktorleis/job)

## Setting up gurobi

A gurobi licence is necessary to the project so be sure to go to the gurobi website to set up your licence.

Tip : For docker use `WLS Compute Server` licence

## RedBench

In the [run.py](dataset/redbench/run.py) file change the DEFAULT_PSQL constant

## Runnning

```bash
python make_each_sqlfile.py
python sqljson.py

python experiment.py
```

## Method

- step 0.1 (optional): `python make_each_sqlfile.py` : puts sql files from ceb and job into a folder to rewrite later, only needs to be done once
- step 0.2 (optional): `python sqljson.py` : turn sql files into json files, only needs to be done once
- step 1: `python compare_bata.py`
- step 2: `python re_sql_exe.py <ilp>` : creates mv scripts and rewrites queries
- step 3: `bash run_mv.sh` : creates mv
- step 4: `python setup_rewritten.py <ilp>` : will use the csv and rewritten queries to setup the proper workloads according to frequency
- step 5: `python run.py` : runs redbench with new workload

## Docker setup

Run `setup.sh` in data folder before building image.

Setup docker image
```bash
docker build -t rs_db_exp:1.0 .

docker run -ti --volume postgres_data:/var/lib/postgresql/data --volume python_data:/home/paolo/rs_db_system --name mv_exp rs_db_exp:1.0
```

Then enter the container:

```bash
docker exec -ti mv_exp bash
```
