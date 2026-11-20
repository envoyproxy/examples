#!/bin/bash -e

export NAME=zipkin

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Make a request to service-1"
# the proxy Envoy has no healthcheck; retry the first request until it is serving.
wait_for 10 bash -c "responds_with 'Hello from behind Envoy (service 1)!' http://localhost:${PORT_PROXY}/trace/1"

run_log "Make a request to service-2"
# service-2 is reached via envoy-2, a separate container with no healthcheck; retry until it is up.
wait_for 10 bash -c "responds_with 'Hello from behind Envoy (service 2)!' http://localhost:${PORT_PROXY}/trace/2"

run_log "View the traces in Zipkin UI"
responds_with \
    "<!DOCTYPE html>" \
    "http://localhost:${PORT_UI}/zipkin/"
