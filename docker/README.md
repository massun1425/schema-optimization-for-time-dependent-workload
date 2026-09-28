# PostgreSQL container for the experiments

Creates the same environment as the container that produced the results of the paper
(`mv_postgres`, image `imdb-postgres`, built on 2026-05-24).

| File | Content |
|---|---|
| `../Dockerfile` | Image definition (PostgreSQL 18.4 + IMDB data + server parameters) |
| `schema.sql` | IMDB table definitions (executed on the first start; identical to the one in the running image) |
| `create_container.sh` | Build → start → wait for the initialization → verify |
| `verify_env.sh` | Checks that a container matches the experimental environment (read-only) |
| `../.dockerignore` | Restricts the build context to `docker/schema.sql` |

## Experimental environment

| Item | Value |
|---|---|
| PostgreSQL | 18.4 (`postgres:18.4-trixie`, 18.4-1.pgdg13+1) |
| Container resources | 8 cores (CPUs 0-7), 16 GiB memory, 4 GiB shm, port 5432 |
| Server parameters | shared_buffers=2GB, effective_cache_size=8GB, work_mem=128MB, maintenance_work_mem=1GB, random_page_cost=1.1, effective_io_concurrency=200, max_parallel_workers=8, max_parallel_workers_per_gather=2, max_parallel_maintenance_workers=2, jit=off, max_locks_per_transaction=256 |
| Data | IMDB (JOB version, https://event.cwi.nl/da/job/imdb.tgz), 21 tables, 44 indexes (21 primary keys + 23 additional) |

`verify_env.sh` checks all of these as well as the row counts of every table.

## Usage

```bash
# Create a new container (exits without doing anything if mv_postgres already exists)
bash docker/create_container.sh

# Create one next to the existing container and check that they match
# (the experiment code uses mv_postgres:5432, so this is only for checking)
NAME=mv_postgres_new PORT=5433 bash docker/create_container.sh

# Verify an existing container
bash docker/verify_env.sh mv_postgres
```

## Notes

- The base image is pinned by the tag `postgres:18.4-trixie`. The original image was built
  from the `postgres:latest` of that time (built on 2026-05-20) whose digest is no longer
  available, so the exact versions of OS packages may differ. The PostgreSQL version,
  settings, data and indexes can be checked with `verify_env.sh`.
- The IMDB data is downloaded from an external URL during the build.
- The running container also contains MVs created by the experiments and a test table
  (`test_dist`); they are not inputs of the experiments and are not part of the reproduction.
