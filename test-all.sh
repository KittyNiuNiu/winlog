#!/usr/bin/env bash
# Runs all unit and integration tests with one command (#73):
#   1. backend unit tests         uv run pytest tests/unit         (in backend/)
#   2. backend integration tests  uv run pytest tests/integration  (in backend/)
#   3. frontend tests             npm test                         (in frontend/)
#
# Every suite runs, even after one fails. A summary at the end lists each suite as passed or
# failed, and the exit code is 0 only when all of them pass.
#
# The integration tests need the PostgreSQL test database. The script starts it with
# `docker compose up -d --wait db` and, only if it was not running before, stops it again at
# the end with `docker compose stop db`, also after a failure or Ctrl+C. It never removes
# containers or volumes, and it does not change .env.
#
# Needs: .env in the repository root (copy .env.example), Docker, uv, and `npm ci` done in
# frontend/. It installs nothing itself (`uv run` syncs the backend's environment on its own).
# Works with bash 3.2 (macOS), Linux, WSL and Git Bash. Run it from anywhere:
# ./test-all.sh in the repository root, or by its path from another folder.

# The repository root is the folder this script is in.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)" || exit 1
cd "$ROOT" || exit 1

if [ ! -f "$ROOT/.env" ]; then
  echo "test-all.sh: no .env in $ROOT." >&2
  echo "Copy .env.example to .env first: cp .env.example .env" >&2
  exit 1
fi

# Suite names and results, in run order (indexed arrays work in bash 3.2).
SUITE_NAMES=()
SUITE_RESULTS=()

record() {
  SUITE_NAMES+=("$1")
  SUITE_RESULTS+=("$2")
}

heading() {
  echo
  echo "==> $1"
  echo
}

# --- Test database -----------------------------------------------------------------------

db_is_running() {
  command -v docker >/dev/null 2>&1 || return 1
  docker compose ps --status running --services db 2>/dev/null | grep -qx db
}

STARTED_DB=0

stop_db_if_started() {
  if [ "$STARTED_DB" = 1 ]; then
    STARTED_DB=0
    echo
    echo "==> Stopping the test database (this script started it)"
    docker compose stop db || echo "test-all.sh: could not stop the db service." >&2
  fi
}

# On every exit, normal, failed or interrupted, stop the database if this script started it.
trap stop_db_if_started EXIT
trap 'echo; echo "test-all.sh: interrupted." >&2; exit 130' INT
trap 'exit 143' TERM

start_db() {
  if db_is_running; then
    echo "The test database is already running; it stays running."
    return 0
  fi
  if ! command -v docker >/dev/null 2>&1; then
    echo "test-all.sh: the test database could not be started: docker is not installed." >&2
    return 1
  fi
  # Started by this script from here on, so it is stopped again even if starting fails halfway.
  STARTED_DB=1
  if ! docker compose up -d --wait db; then
    echo "test-all.sh: the test database could not be started (docker compose up -d --wait db failed)." >&2
    echo "Check that Docker is running and port 5432 is free." >&2
    return 1
  fi
  return 0
}

# --- Suites ------------------------------------------------------------------------------

# run_suite NAME FOLDER COMMAND...: runs COMMAND in FOLDER and records the result.
run_suite() {
  local name="$1" folder="$2"
  shift 2
  (cd "$ROOT/$folder" && "$@")
  if [ $? -eq 0 ]; then
    record "$name" passed
  else
    record "$name" failed
  fi
}

heading "Backend unit tests (uv run pytest tests/unit)"
if command -v uv >/dev/null 2>&1; then
  run_suite "Backend unit tests" backend uv run pytest tests/unit
else
  echo "test-all.sh: uv is not installed. See https://docs.astral.sh/uv/." >&2
  record "Backend unit tests" failed
fi

heading "Backend integration tests (uv run pytest tests/integration)"
if ! command -v uv >/dev/null 2>&1; then
  echo "test-all.sh: uv is not installed. See https://docs.astral.sh/uv/." >&2
  record "Backend integration tests" failed
elif start_db; then
  run_suite "Backend integration tests" backend uv run pytest tests/integration
else
  echo "test-all.sh: the test database could not be started, so the integration tests did not run." >&2
  record "Backend integration tests" failed
fi

heading "Frontend tests (npm test)"
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  echo "test-all.sh: frontend/node_modules is missing. Run 'npm ci' in frontend/ first." >&2
  record "Frontend tests" failed
elif ! command -v npm >/dev/null 2>&1; then
  echo "test-all.sh: npm is not installed. Install Node from frontend/.nvmrc." >&2
  record "Frontend tests" failed
else
  run_suite "Frontend tests" frontend npm test
fi

stop_db_if_started

# --- Summary -----------------------------------------------------------------------------

echo
echo "==> Summary"
EXIT_CODE=0
i=0
while [ "$i" -lt "${#SUITE_NAMES[@]}" ]; do
  printf '  %-28s %s\n' "${SUITE_NAMES[$i]}" "${SUITE_RESULTS[$i]}"
  [ "${SUITE_RESULTS[$i]}" = passed ] || EXIT_CODE=1
  i=$((i + 1))
done

if [ "$EXIT_CODE" -eq 0 ]; then
  echo "All test suites passed."
else
  echo "Some test suites failed."
fi
exit "$EXIT_CODE"
