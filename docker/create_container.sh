#!/bin/bash
# ======================================================================
# Creates a PostgreSQL container identical to the experimental environment of the paper.
#
#   1) Build the image from the Dockerfile (PostgreSQL 18.4 + IMDB data + server parameters)
#   2) Start the container with the same resource limits as in the experiments
#        8 cores (CPUs 0-7) / 16 GiB memory / 4 GiB shm / port 5432
#   3) Wait until the first-start initialization (schema -> CSV load -> indexes) has finished
#   4) Verify with docker/verify_env.sh that it matches the experimental environment
#
# The experiment code (utils/postgres_executor.py, config/default.yaml) assumes the
# container name mv_postgres and port 5432, so these are the defaults.
# If a container with the same name already exists, the script exits without doing
# anything (existing containers are never removed).
#
# Usage:
#   bash docker/create_container.sh
#   NAME=mv_postgres_new PORT=5433 bash docker/create_container.sh   # side by side with an existing one (for checking)
#
# Environment variables:
#   IMAGE   image name to build (default: imdb-postgres:18.4; an existing imdb-postgres:latest is left untouched)
#   NAME    container name (default: mv_postgres)
#   PORT    host port (default: 5432)
#   CPUSET  CPUs to use (default: 0-7)
#
# Note: the build downloads the IMDB data (about 1.2 GB) from https://event.cwi.nl/da/job/imdb.tgz.
#       The initialization (load and index creation) takes tens of minutes.
# ======================================================================
set -u -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
cd "${HERE}/.." || exit 1

IMAGE="${IMAGE:-imdb-postgres:18.4}"
NAME="${NAME:-mv_postgres}"
PORT="${PORT:-5432}"
CPUSET="${CPUSET:-0-7}"

log() { echo "[$(date '+%F %T')] $*"; }
die() { log "ERROR: $*"; exit 1; }

if docker inspect "${NAME}" > /dev/null 2>&1; then
    die "Container ${NAME} already exists. To recreate it, stop and rename the existing one manually
       (e.g. docker stop ${NAME} && docker rename ${NAME} ${NAME}_old)"
fi

log "Building the image: ${IMAGE}"
docker build -t "${IMAGE}" . || die "docker build failed"

log "Starting the container: ${NAME} (port ${PORT}, cpuset ${CPUSET})"
docker run -d \
    --name "${NAME}" \
    --shm-size=4g \
    --cpuset-cpus="${CPUSET}" \
    --memory=16g \
    -p "${PORT}:5432" \
    "${IMAGE}" > /dev/null || die "docker run failed"

# The init scripts run on a temporary server that is restarted as the real server
# afterwards. pg_isready already answers during that phase, so the completion
# message in the log is used instead.
log "Waiting for the initialization (schema -> CSV load -> indexes) to finish..."
until docker logs "${NAME}" 2>&1 | grep -q "PostgreSQL init process complete; ready for start up."; do
    if [ "$(docker inspect -f '{{.State.Running}}' "${NAME}")" != "true" ]; then
        docker logs --tail 30 "${NAME}"
        die "The container stopped during initialization (see the log above)"
    fi
    sleep 30
done
until docker exec "${NAME}" pg_isready -U postgres > /dev/null 2>&1; do
    sleep 2
done
log "Initialization finished"

bash "${HERE}/verify_env.sh" "${NAME}"
