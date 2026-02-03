#!/bin/bash -e

export NAME=http-filter-cc
export PORT_PROXY="${HTTP_FILTER_CC_PORT_PROXY:-10000}"
export UID

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Build custom Envoy binary with filter"
"${DOCKER_COMPOSE[@]}" run --rm envoy-build

run_log "Check that binary was created"
ls -lh bin/envoy

run_log "Test custom header is added by the filter"
responds_with_header \
    "x-custom-header: custom-value" \
    "http://localhost:${PORT_PROXY}/"

run_log "Test that the backend receives the request"
responds_with \
    "Request served by" \
    "http://localhost:${PORT_PROXY}/"
