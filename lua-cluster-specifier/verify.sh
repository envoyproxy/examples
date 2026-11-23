#!/bin/bash -e

export NAME=lua-cluster-specifier

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Test Lua cluster specifier with normal cluster"
# the proxy has no healthcheck; retry until it is serving.
wait_for 10 bash -c "responds_with_header 'HTTP/1.1 200 OK' http://localhost:${PORT_PROXY}/"

run_log "Test Lua cluster specifier with fake cluster"
responds_with_header \
    "HTTP/1.1 503 Service Unavailable" \
    "http://localhost:${PORT_PROXY}/" \
    -H 'header_key: fake'
