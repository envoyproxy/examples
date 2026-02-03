#!/bin/bash -e

export NAME=http-filter-cc
export PORT_PROXY="${HTTP_FILTER_CC_PORT_PROXY:-10000}"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Test custom header is added by the filter"
responds_with_header \
    "x-custom-header: custom-value" \
    "http://localhost:${PORT_PROXY}/"

run_log "Test that the backend receives the request"
responds_with \
    "Request served by" \
    "http://localhost:${PORT_PROXY}/"
