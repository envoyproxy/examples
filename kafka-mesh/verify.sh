#!/bin/bash -e

export NAME=kafka-mesh
export PORT_PROXY="${KAFKA_MESH_PORT_PROXY:-11200}"
export PORT_ADMIN="${KAFKA_MESH_PORT_ADMIN:-11201}"

UPARGS="proxy kafka-cluster1 kafka-cluster2 zookeeper"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

kafka_client () {
    "${DOCKER_COMPOSE[@]}" run --rm kafka-client "$@"
}

run_log "Produce message to topic 'apples' (routes to cluster1)"
kafka_client /bin/bash -c "echo 'hello from apples' | kafka-console-producer --broker-list proxy:10000 --topic apples"

run_log "Produce message to topic 'bananas' (routes to cluster2)"
kafka_client /bin/bash -c "echo 'hello from bananas' | kafka-console-producer --broker-list proxy:10000 --topic bananas"

run_log "Verify message landed in cluster1 (consume directly from cluster1)"
kafka_client kafka-console-consumer --bootstrap-server kafka-cluster1:9092 --topic apples --from-beginning --max-messages 1 | grep "hello from apples"

run_log "Verify message landed in cluster2 (consume directly from cluster2)"
kafka_client kafka-console-consumer --bootstrap-server kafka-cluster2:9092 --topic bananas --from-beginning --max-messages 1 | grep "hello from bananas"

run_log "Consume 'apples' through mesh filter"
kafka_client kafka-console-consumer --bootstrap-server proxy:10000 --topic apples --from-beginning --max-messages 1 | grep "hello from apples"

run_log "Consume 'bananas' through mesh filter"
kafka_client kafka-console-consumer --bootstrap-server proxy:10000 --topic bananas --from-beginning --max-messages 1 | grep "hello from bananas"

run_log "Check Envoy stats for produce requests"
_curl "http://localhost:${PORT_ADMIN}/stats?filter=kafka" | grep "produce_request" | grep -v ": 0"

run_log "Check Envoy stats for fetch requests"
_curl "http://localhost:${PORT_ADMIN}/stats?filter=kafka" | grep "fetch_request" | grep -v ": 0"
