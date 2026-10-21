#!/bin/sh
# Start-up steps for the API container.
set -eu

echo "Applying database migrations..."
alembic upgrade head

# The app logs one JSON line per request itself, so uvicorn's access log is off.
exec uvicorn policypal.api.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log
