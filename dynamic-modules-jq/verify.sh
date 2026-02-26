#!/bin/bash -e

export NAME=dynamic-modules-jq
export PORT_PROXY="${DYNAMIC_MODULES_JQ_PORT_PROXY:-10530}"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

wait_for 30 bash -c "responds_with 'POST' http://localhost:${PORT_PROXY}"

run_log "Send a request with sensitive fields — the password should be stripped before reaching upstream"
responds_with \
    "alice" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"user":"alice","password":"s3cr3t"}' \
    "http://localhost:${PORT_PROXY}"

run_log "Verify the password value is absent from what the upstream echoed back"
responds_without \
    "s3cr3t" \
    -X POST \
    -H "Content-Type: application/json" \
    -d '{"user":"alice","password":"s3cr3t"}' \
    "http://localhost:${PORT_PROXY}"

run_log "Non-JSON bodies pass through unchanged"
responds_with \
    "hello" \
    -X POST \
    -H "Content-Type: text/plain" \
    -d "hello" \
    "http://localhost:${PORT_PROXY}"
