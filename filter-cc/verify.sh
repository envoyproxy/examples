#!/bin/bash -e

export NAME=filter-cc
export MANUAL=true
export UID


# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Build the Envoy binary with the sample filter statically linked"
"${DOCKER_COMPOSE[@]}" -f docker-compose-build.yaml run --quiet-pull --remove-orphans filter_build

run_log "Check the compiled binary"
ls -l bin/envoy

bring_up_example

run_log "Test connection"
wait_for 10 bash -c "\
         responds_with \
         'Request served by' \
         http://localhost:8000"

run_log "Test the sample filter has added its header to the proxied request"
responds_with \
    "Via: sample-filter" \
    http://localhost:8000
