#!/bin/bash -e

export NAME=opentelemetry

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

# The front proxy has no healthcheck, so `compose up --wait` returns before its listener is up.
wait_for 10 bash -c "responds_with Hello http://localhost:${PORT_PROXY}/trace/1"

run_log "Make a request to service-1"
responds_with \
    "Hello from behind Envoy (service 1)!" \
    "http://localhost:${PORT_PROXY}/trace/1"

run_log "Make a request to service-2"
responds_with \
    "Hello from behind Envoy (service 2)!" \
    "http://localhost:${PORT_PROXY}/trace/2"

run_log "View the traces in OpenTelemetry UI"
responds_with \
    "<!DOCTYPE html>" \
    "http://localhost:${PORT_UI}/debug/tracez"
