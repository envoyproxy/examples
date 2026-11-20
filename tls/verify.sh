#!/bin/bash -e

export NAME=tls

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Test https -> http"
# each proxy is a separate Envoy container with no healthcheck, so `compose up --wait` can return
# before it is serving; retry each proxy's first request until it is up.
wait_for 10 bash -c "responds_with '\"x-forwarded-proto\": \"https\",' -k https://localhost:${PORT_PROXY0}"
curl -sk "https://localhost:${PORT_PROXY0}"  | jq  '.hostname' | grep '"service-http"'

run_log "Test https -> https"
wait_for 10 bash -c "responds_with '\"x-forwarded-proto\": \"https\",' -k https://localhost:${PORT_PROXY1}"
curl -sk "https://localhost:${PORT_PROXY1}"  | jq  '.hostname' | grep '"service-https"'

run_log "Test http -> https"
wait_for 10 bash -c "responds_with '\"x-forwarded-proto\": \"http\",' http://localhost:${PORT_PROXY2}"
curl -s "http://localhost:${PORT_PROXY2}"  | jq  '.hostname' | grep '"service-https"'

run_log "Test https passthrough"
# `responds_without` is satisfied by a refused connection (empty body lacks the header), so gate on a
# successful response first, then assert the header is absent.
wait_for 10 bash -c "curl -fsk https://localhost:${PORT_PROXY3} -o /dev/null"
responds_without \
    '"x-forwarded-proto"' \
    -k \
    "https://localhost:${PORT_PROXY3}"
curl -sk "https://localhost:${PORT_PROXY3}"  | jq  '.hostname' | grep '"service-https"'
