#!/bin/sh
# Start-up for the Ollama container: run the server, and download PULL_MODEL the
# first time (it is then kept in the ollama volume, so later starts work offline).
#
# The download happens here rather than in a separate one-off container because
# `docker compose up --wait` treats any container that exits as a failure.
set -u

ollama serve &
server=$!
# Pass `docker compose stop` on to the server so it shuts down cleanly.
trap 'kill "$server"; wait "$server"; exit 0' TERM INT

# Wait for the server to answer, but stop if it has already exited (e.g. a broken volume),
# so the failure shows up at once instead of as a container stuck in "starting".
until ollama list > /dev/null 2>&1; do
  if ! kill -0 "$server" 2> /dev/null; then
    echo "The Ollama server did not start." >&2
    exit 1
  fi
  sleep 1
done

if ! ollama show "$PULL_MODEL" > /dev/null 2>&1; then
  echo "Downloading $PULL_MODEL (first start only)..."
  # If the download fails (e.g. no internet), keep serving: the API quotes the policy
  # text instead, and the healthcheck stays unhealthy until the model is there.
  ollama pull "$PULL_MODEL" || echo "Could not download $PULL_MODEL." >&2
fi

wait "$server"
