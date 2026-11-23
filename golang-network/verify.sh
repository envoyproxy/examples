#!/bin/bash -e

export NAME=golang-network
export UID
export MANUAL=true

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Compile the go plugin library"
"${DOCKER_COMPOSE[@]}" -f docker-compose-go.yaml up --quiet-pull --remove-orphans go_plugin_compile

run_log "Start all of our containers"
bring_up_example

run_log "Send tcp data handled by the Go plugin"
# the proxy has no healthcheck; retry the send until it is serving and the echo lands.
wait_for 10 bash -c "echo -n world | nc -w1 127.0.0.1 ${PORT_PROXY}; ${DOCKER_COMPOSE[*]} logs echo_service | grep -q 'hello, world'"

run_log "Check echo server log"
"${DOCKER_COMPOSE[@]}" logs echo_service | grep "hello, world"
