#!/bin/bash -e

export NAME=udp

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Send some UDP packets"
# the proxy has no healthcheck; retry the first packet until it reaches the backend.
wait_for 10 bash -c "echo -n HELO | nc -4u -w1 127.0.0.1 ${PORT_PROXY}; ${DOCKER_COMPOSE[*]} logs service-udp | grep -q HELO"
echo -n OLEH | nc -4u -w1 127.0.0.1 "${PORT_PROXY}"

run_log "Check backend log"
"${DOCKER_COMPOSE[@]}" logs service-udp | grep HELO
"${DOCKER_COMPOSE[@]}" logs service-udp | grep OLEH

run_log "Check admin stats"
curl -s "http://127.0.0.1:${PORT_ADMIN}/stats" | grep udp | grep -v "\: 0"
