#!/bin/bash -e

export NAME=http-filter-cc
export PORT_PROXY="${HTTP_FILTER_CC_PORT_PROXY:-10000}"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Test custom header is added by the filter"
responds_with \
    '"x-custom-header": "custom-value"' \
    "http://localhost:${PORT_PROXY}/"

run_log "Test per-route configuration override"
responds_with \
    '"x-overridden-header": "overridden-value"' \
    "http://localhost:${PORT_PROXY}/override"

run_log "Test that the backend receives the request"
responds_with \
    '"hostname": "echo"' \
    "http://localhost:${PORT_PROXY}/"
