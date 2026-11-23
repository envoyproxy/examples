#!/bin/bash -e

export NAME=datadog-tracing

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Make a request to http service"
# the proxy has no healthcheck; retry until it is serving.
wait_for 10 bash -c "responds_with_header 'x-datadog-trace-id' http://localhost:${PORT_PROXY}"
