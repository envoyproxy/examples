#!/bin/bash -e

export NAME=grpc-bridge
# this allows us to bring up the stack manually after generating stubs
export MANUAL=true

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"


run_log "Generate protocol stubs"
"${DOCKER_COMPOSE[@]}" -f docker-compose-protos.yaml up --quiet-pull --build

ls client/kv/kv_pb2.py
ls server/kv/kv.pb.go

bring_up_example

# `--wait` only tells us the containers are running. The client proxy resolves the
# server proxy when it starts, and until that resolves the bridge answers with an
# empty 200 - which `set` does not check - so probe with a round-trip first.
run_log "Wait for the key-value service"
wait_for 10 bash -c "\
    ${DOCKER_COMPOSE[*]} exec -T grpc-client /client/grpc-kv-client.py set ping pong \
    && ${DOCKER_COMPOSE[*]} exec -T grpc-client /client/grpc-kv-client.py get ping \
       | grep pong"

run_log "Set key value foo=bar"
"${DOCKER_COMPOSE[@]}" exec -T grpc-client /client/grpc-kv-client.py set foo bar | grep setf

run_log "Get key foo"
"${DOCKER_COMPOSE[@]}" exec -T grpc-client /client/grpc-kv-client.py get foo | grep bar
