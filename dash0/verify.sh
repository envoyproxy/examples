#!/bin/bash -e

export NAME=dash0
export PORT_PROXY="${DASH0_PORT_PROXY:-10800}"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Make a request to service-1"
responds_with \
    "Hello from behind Envoy (service 1)!" \
    "http://localhost:${PORT_PROXY}/trace/1"
