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

run_log "View the traces in the collector's debug output"
# The collector's `debug` exporter logs the spans it receives to its stdout. Each request
# produced a trace; its spans appear once the batch processor flushes (a second or two).
check_span () {
    "${DOCKER_COMPOSE[@]}" logs opentelemetry | grep -q "$1"
}
for span in routeToEnvoy1 routeToEnvoy2ViaEnvoy1; do
    for _ in $(seq 1 15); do
        check_span "$span" && break
        sleep 1
    done
    "${DOCKER_COMPOSE[@]}" logs opentelemetry | grep "$span"
done
