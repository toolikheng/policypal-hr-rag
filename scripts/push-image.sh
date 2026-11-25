#!/bin/sh
# Push an image that has already been scanned, and prove the registry got that image.
#
# Usage: sh scripts/push-image.sh <scanned image ID> <name:tag> [<name:tag> ...]
#
# For each tag: the tag must point at the scanned image ID (nothing was rebuilt or
# re-tagged since the scan), then it is pushed, then the digest the registry now serves
# for the tag must equal the digest Docker recorded for the image when pushing it.
set -eu

if [ "$#" -lt 2 ]; then
    echo "usage: sh scripts/push-image.sh <scanned image ID> <name:tag> [<name:tag> ...]" >&2
    exit 2
fi
scanned_id=$1
shift

# Check every tag before pushing any, so a mismatch publishes nothing.
for ref in "$@"; do
    local_id=$(docker image inspect --format '{{.Id}}' "$ref")
    if [ "$local_id" != "$scanned_id" ]; then
        echo "$ref is $local_id, not the scanned image $scanned_id" >&2
        exit 1
    fi
done

for ref in "$@"; do
    docker push "$ref"

    # RepoDigests lists "<repository>@<digest>" for each registry the image was pushed to.
    repository=${ref%:*}
    pushed=""
    for entry in $(docker image inspect --format '{{join .RepoDigests " "}}' "$scanned_id"); do
        if [ "${entry%@*}" = "$repository" ]; then
            pushed=${entry#*@}
        fi
    done
    if [ -z "$pushed" ]; then
        echo "Docker recorded no pushed digest for $repository" >&2
        exit 1
    fi

    remote=$(docker buildx imagetools inspect "$ref" --format '{{.Manifest.Digest}}')
    if [ "$remote" != "$pushed" ]; then
        echo "The registry serves $remote for $ref, not the pushed image $pushed" >&2
        exit 1
    fi
    echo "Pushed $ref = $pushed (image $scanned_id)"
done
