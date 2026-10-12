#!/bin/bash -e

export NAME=tls

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Test https -> http"
responds_with \
    '"x-forwarded-proto": "https",' \
    -k \
    "https://localhost:${PORT_PROXY0}"
curl -sk "https://localhost:${PORT_PROXY0}"  | jq  '.hostname' | grep '"service-http"'

run_log "Test https -> https"
responds_with \
    '"x-forwarded-proto": "https",' \
    -k \
    "https://localhost:${PORT_PROXY1}"
curl -sk "https://localhost:${PORT_PROXY1}"  | jq  '.hostname' | grep '"service-https"'

run_log "Test http -> https"
responds_with \
    '"x-forwarded-proto": "http",' \
    "http://localhost:${PORT_PROXY2}"
curl -s "http://localhost:${PORT_PROXY2}"  | jq  '.hostname' | grep '"service-https"'

run_log "Test https passthrough"
responds_without \
    '"x-forwarded-proto"' \
    -k \
    "https://localhost:${PORT_PROXY3}"
curl -sk "https://localhost:${PORT_PROXY3}"  | jq  '.hostname' | grep '"service-https"'
