#!/bin/bash
# ======================================================================
# Verifies that a container matches the experimental environment of the paper
# (read-only; the DB is not modified).
#
# The expected values were recorded from the container that produced the paper
# results (imdb-postgres, built on 2026-05-24):
#   - container resources: 8 cores (CPUs 0-7), 16 GiB memory, 4 GiB shm, port 5432
#   - PostgreSQL 18.4 and the server parameters (CMD in the Dockerfile)
#   - row counts of the 21 IMDB tables, 44 indexes (21 primary keys + 23 additional)
#
# Usage: bash docker/verify_env.sh [container name]   (default: mv_postgres)
# Exit code: 0 = everything matches, 1 = mismatch found
# ======================================================================
set -u -o pipefail

NAME="${1:-mv_postgres}"
FAIL=0

ok()   { echo "  OK   $*"; }
ng()   { echo "  NG   $*"; FAIL=1; }
check() {  # check <item> <actual value> <expected value>
    if [ "$2" = "$3" ]; then ok "$1 = $2"; else ng "$1 = $2 (expected: $3)"; fi
}
q() { docker exec "${NAME}" psql -U postgres -d imdbload -Atc "$1"; }

docker inspect "${NAME}" > /dev/null 2>&1 || { echo "Container not found: ${NAME}"; exit 1; }

echo "== Container resources (${NAME})"
check "CPUs (cpuset)" "$(docker inspect -f '{{.HostConfig.CpusetCpus}}' "${NAME}")" "0-7"
check "memory limit"  "$(docker inspect -f '{{.HostConfig.Memory}}' "${NAME}")"     "17179869184"
check "shm size"      "$(docker inspect -f '{{.HostConfig.ShmSize}}' "${NAME}")"    "4294967296"
check "host port"     "$(docker inspect -f '{{(index (index .HostConfig.PortBindings "5432/tcp") 0).HostPort}}' "${NAME}")" "5432"

echo "== PostgreSQL"
check "server_version" "$(q 'show server_version' | cut -d' ' -f1)" "18.4"
while read -r KEY VAL; do
    check "${KEY}" "$(q "show ${KEY}")" "${VAL}"
done <<'EOF'
shared_buffers 2GB
effective_cache_size 8GB
work_mem 128MB
maintenance_work_mem 1GB
random_page_cost 1.1
effective_io_concurrency 200
max_parallel_workers 8
max_parallel_workers_per_gather 2
max_parallel_maintenance_workers 2
jit off
max_locks_per_transaction 256
EOF

echo "== Row counts of the IMDB tables"
while read -r TBL CNT; do
    check "${TBL}" "$(q "select count(*) from ${TBL}")" "${CNT}"
done <<'EOF'
aka_name 901343
aka_title 361472
cast_info 36244344
char_name 3140339
comp_cast_type 4
company_name 234997
company_type 4
complete_cast 135086
info_type 113
keyword 134170
kind_type 7
link_type 18
movie_companies 2609129
movie_info 14835720
movie_info_idx 1380035
movie_keyword 4523930
movie_link 29997
name 4167491
person_info 2963664
role_type 12
title 2528312
EOF

echo "== Indexes"
TABLES="'aka_name','aka_title','cast_info','char_name','comp_cast_type','company_name','company_type','complete_cast','info_type','keyword','kind_type','link_type','movie_companies','movie_info','movie_info_idx','movie_keyword','movie_link','name','person_info','role_type','title'"
check "number of indexes on the IMDB tables" \
    "$(q "select count(*) from pg_indexes where schemaname='public' and tablename in (${TABLES})")" "44"
EXPECTED_IDX="company_id_movie_companies company_type_id_movie_companies info_type_id_movie_info info_type_id_movie_info_idx info_type_id_person_info keyword_id_movie_keyword kind_id_aka_title kind_id_title link_type_id_movie_link linked_movie_id_movie_link movie_id_aka_title movie_id_cast_info movie_id_complete_cast movie_id_movie_companies movie_id_movie_info movie_id_movie_info_idx movie_id_movie_keyword movie_id_movie_link person_id_aka_name person_id_cast_info person_id_person_info person_role_id_cast_info role_id_cast_info"
check "names of the 23 additional indexes" \
    "$(q "select string_agg(indexname, ' ' order by indexname) from pg_indexes where schemaname='public' and tablename in (${TABLES}) and indexname not like '%_pkey'")" \
    "${EXPECTED_IDX}"

echo
if [ ${FAIL} -eq 0 ]; then
    echo "Result: matches the experimental environment of the paper"
else
    echo "Result: mismatch found (check the NG items)"
fi
exit ${FAIL}
