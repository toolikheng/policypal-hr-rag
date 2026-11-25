#!/bin/sh
# Fail if a local Docker image has a HIGH or CRITICAL vulnerability that has a fix.
# CI, CD and `make image-scan` all run this script, so the gate has one set of settings.
#
# Usage: sh scripts/scan-image.sh <image ID or name:tag>
#
# Trivy runs from its official image, pinned by digest (not a tag, which can be moved),
# and reads the image from the local Docker daemon. Its vulnerability database is
# downloaded on each run into a Docker volume, so repeated local scans are faster.
set -eu

TRIVY_IMAGE="aquasec/trivy:0.75.0@sha256:af6acf9a6b85dfe389a1941505c0ce9efef52a4719635e1a962f022a3d855daa"

if [ "$#" -ne 1 ]; then
    echo "usage: sh scripts/scan-image.sh <image ID or name:tag>" >&2
    exit 2
fi

# --ignore-unfixed: only vulnerabilities with a fixed version count (they can be fixed now).
exec docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v policypal-trivy-cache:/root/.cache/trivy \
    "$TRIVY_IMAGE" image \
    --severity HIGH,CRITICAL --ignore-unfixed --scanners vuln --exit-code 1 \
    "$1"
