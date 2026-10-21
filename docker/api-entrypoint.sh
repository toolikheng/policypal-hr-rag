#!/bin/sh
# Start-up steps for the API container. All output is JSON log lines.
set -eu

alembic upgrade head

# The app logs one JSON line per request itself, so uvicorn's access log is off.
exec uvicorn policypal.api.main:create_app_from_env --factory --host 0.0.0.0 --port 8000 --no-access-log
