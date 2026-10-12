#!/bin/bash -e

export NAME=jaeger-tracing

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

wait_for 10 bash -c "responds_with Hello http://localhost:${PORT_PROXY}/trace/1"

run_log "Test services"
responds_with \
    Hello \
    "http://localhost:${PORT_PROXY}/trace/1"

run_log "Test Jaeger UI"
responds_with \
    "<!doctype html>" \
    "http://localhost:${PORT_UI}"
