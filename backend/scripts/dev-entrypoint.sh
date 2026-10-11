#!/bin/sh
# Local development entrypoint: create database and least-privilege user, apply migrations,
# then run the API with hot reload. Production runs migrations as a separate Container Apps job.
set -eu
echo "[dev-entrypoint] waiting for database and initializing"
python -m app.cli db-init
echo "[dev-entrypoint] applying migrations"
alembic upgrade head
echo "[dev-entrypoint] starting API"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-proxy-headers --reload --reload-dir app
