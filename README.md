# RS DB SYSTEM

## Installation

Before doing anything make sure to install all the modules (Check [requirements.txt](requirements.txt))

To install the required modules simply execute this commanddoc

```
pip install -r requirements.txt
```

## PostgreSQL server setup

Run `setup.sh` in data folder then run `psql -U postgres < setup.sql`.

[JOB](https://github.com/viktorleis/job)

## Setting up gurobi

A gurobi licence is necessary to the project so be sure to go to the gurobi website to set up your licence.

Tip : For docker use `WLS Compute Server` licence

## RedBench

In the [run.py](dataset/redbench/run.py) file change the DEFAULT_PSQL constant

## Runnning experiment

```bash
python make_each_sqlfile.py
python sqljson.py

chmod +777 make_dirs.sh
./make_dirs.sh

python experiment.py
```

## Docker setup

Run `setup.sh` in data folder before building image.

Setup docker image
```bash
docker build -t rs_db_exp:1.0 .

docker run -ti -d --shm-size=1g --volume postgres_data:/var/lib/postgresql/data --volume python_data:/home/user/rs_db_system --name mv_exp rs_db_exp:1.0
```

Then enter the container:

```bash
docker exec -ti mv_exp bash
cd data
psql -U postgres < setup.sql
```

Then [run the program](#runnning)

## Method

Method for redbench experiment:

- step 0.1 (optional): `python make_each_sqlfile.py` : puts sql files from ceb and job into a folder to rewrite later, only needs to be done once
- step 0.2 (optional): `python sqljson.py` : turn sql files into json files, only needs to be done once
- step 1: `python compare_bata.py`
- step 2: `python re_sql_exe.py <ilp> mv` : creates mv scripts
- step 3: `bash run_mv.sh` : creates mv on database, and removes the ones that timed out from the mv list
- step 4: `python re_sql_exe.py <ilp>` : rewrites queries
- step 5: `python setup_rewritten.py <ilp>` : will use the csv and rewritten queries to setup the proper workloads according to frequency
- step 6: `python run.py` : runs redbench with new workload

## Other experiments

- `compare_insertquery.py`
- `compare_capacity.py`
- `compare_topk_beta.py`

## How to restart server:

Execute this inside the docker container
```bash
kill -SIGINT 1
```

## IMMV : setting up pg_ivm

See [pg_ivm](https://github.com/sraoss/pg_ivm).

Inside the container:
```bash
wget https://github.com/sraoss/pg_ivm/archive/refs/heads/main.zip
unzip main.zip
apt-get -y install postgresql-server-dev-17
make install

psql -U postgres -c "CREATE EXTENSION pg_ivm;"
echo "shared_preload_libraries = 'pg_ivm'" >> /var/lib/postgresql/data/postgresql.conf
```

Then restart the server

Then start uop the container as usual:
```bash
docker start mv_exp
```

## How to switch experiment from JOB to CEB queries

Change the GET_CEB value in utils.py to True or False (True for CEB and False for JOB)


## How to copy data from host to container

Sometimes you may need to update the container with new programs from your host.

To replace all the files in the container with the new ones, execute the following command

```bash
docker cp /home/user/mv-query-optimization mv_exp:/home/root
```

This will send the **mv-query-optimization** folder to the container

## How to copy data from container to host

To copy output data from container to the current folder, execute the following commands according to what you need.

### redbench output

> docker cp mv_exp:/home/root/mv-query-optimization/Output/redbench .

### compare_bata output

> docker cp mv_exp:/home/root/mv-query-optimization/Output/compare_bata.out .

### run_mv output

> docker cp mv_exp:/home/root/mv-query-optimization/Output/experiment/run_mv .

### execute_rewritten output

> docker cp mv_exp:/home/root/mv-query-optimization/Output/query_rewrite/*.out .

