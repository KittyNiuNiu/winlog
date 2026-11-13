#!/bin/sh
# Starts the backend: the image's CMD runs this on every container start (issue #38), which
# on Render means every deploy and every wake of a sleeping free instance.
#
#   1. Apply the database migrations (alembic upgrade head).
#   2. Reset the demo account, only when DEMO_EMAIL is set and not empty (§7.7, FR-X1).
#   3. Start the server on 0.0.0.0, on the port in PORT, or 8000 when PORT is not set.
#
# If step 1 or 2 fails, the script exits with a non-zero code and the server never starts.
# Render then marks the deploy as failed and keeps serving the previous one.
#
# It reads PORT and DEMO_EMAIL from the process environment only (Render or `docker run -e`),
# never from a .env file. Docker Compose sets neither, so there the backend migrates and then
# serves on 8000, without a demo reset.
#
# Logging: the lines printed here are fixed texts with no customer data. The reset's own
# summary line names the demo email address, so its standard output is not printed; its
# errors still go to standard error. uvicorn gets no --access-log and no --log-config:
# app/telemetry.py turns the access log off, so request lines with query strings (such as
# ?tag=<name>) never reach the log (#11, #74).
set -eu

port="${PORT:-8000}"

echo "start: applying database migrations"
alembic upgrade head

if [ -n "${DEMO_EMAIL:-}" ]; then
  echo "start: resetting the demo account"
  python -m scripts.seed_demo > /dev/null
  echo "start: demo account reset"
else
  echo "start: DEMO_EMAIL is not set, skipping the demo reset"
fi

echo "start: starting the server on port $port"
# exec makes uvicorn the main process, so it receives stop signals directly.
exec uvicorn app.main:app --host 0.0.0.0 --port "$port"
