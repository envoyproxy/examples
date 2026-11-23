#!/bin/bash -e

export NAME=front-proxy

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"


run_log "Test service: localhost:${PORT_PROXY}/service/1"
# front-envoy has no healthcheck, so `compose up --wait` can return before it is serving;
# retry the first request until it is up.
wait_for 10 bash -c "responds_with 'Hello from behind Envoy (service 1)!' http://localhost:${PORT_PROXY}/service/1"

run_log "Test service: localhost:${PORT_PROXY}/service/2"
wait_for 10 bash -c "responds_with 'Hello from behind Envoy (service 2)!' http://localhost:${PORT_PROXY}/service/2"

run_log "Test service: https://localhost:${PORT_HTTPS}/service/1"
wait_for 10 bash -c "responds_with 'Hello from behind Envoy (service 1)!' -k https://localhost:${PORT_HTTPS}/service/1"

run_log "Scale up docker service1=3"
"${DOCKER_COMPOSE[@]}" up --wait -d --scale service1=3

round_robin_service1 () {
    "${DOCKER_COMPOSE[@]}" exec -T front-envoy bash -c "\
        curl -s http://localhost:8080/service/1 \
        && curl -s http://localhost:8080/service/1 \
        && curl -s http://localhost:8080/service/1" \
        | grep Hello | grep "service 1"
}

run_log "Test round-robin localhost:${PORT_PROXY}/service/1"
# the scaled-up service1 replicas take a moment to be discovered by front-envoy;
# retry until the round-robin resolves.
wait_for 10 round_robin_service1

run_log "Test service inside front-envoy: localhost:${PORT_PROXY}/service/2"
wait_for 10 bash -c "${DOCKER_COMPOSE[*]} exec -T front-envoy curl -s http://localhost:8080/service/2 | grep Hello | grep 'service 2'"

run_log "Test service info: localhost:${PORT_STATS}/server_info"
"${DOCKER_COMPOSE[@]}" exec -T front-envoy curl -s "http://localhost:8001/server_info" | jq '.'

run_log "Test service stats: localhost:${PORT_STATS}/stats"
"${DOCKER_COMPOSE[@]}" exec -T front-envoy curl -s "http://localhost:8001/stats" | grep ":"
