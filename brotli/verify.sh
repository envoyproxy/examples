#!/bin/bash -e

export NAME=brotli

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

wait_for 10 bash -c "\
         responds_with_header \
         'content-encoding: br' \
         https://localhost:${PORT_PROXY}/file.json -ki -H 'Accept-Encoding: br'"

run_log "Test service: localhost:${PORT_PROXY}/file.json with compression"
responds_with_header \
    "content-encoding: br" \
    "https://localhost:${PORT_PROXY}/file.json" \
    -ki -H "Accept-Encoding: br"

run_log "Test service: localhost:${PORT_PROXY}/file.txt without compression"
responds_without_header \
    "content-encoding: br" \
    "https://localhost:${PORT_PROXY}/file.txt" \
    -ki -H "Accept-Encoding: br"

run_log "Test service: localhost:${PORT_STATS0}/stats/prometheus without compression"
responds_without_header \
    "content-encoding: br" \
    "http://localhost:${PORT_STATS0}/stats/prometheus" \
    -ki -H "Accept-Encoding: br"

run_log "Test service: localhost:${PORT_STATS1}/stats/prometheus with compression"
responds_with_header \
    "content-encoding: br" \
    "https://localhost:${PORT_STATS1}/stats/prometheus" \
    -ki -H "Accept-Encoding: br"
