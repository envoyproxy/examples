#!/bin/bash -e

export NAME=kafka-mesh
export PORT_PROXY="${KAFKA_MESH_PORT_PROXY:-11110}"
export PORT_ADMIN="${KAFKA_MESH_PORT_ADMIN:-11111}"

UPARGS="proxy kafka-cluster1 kafka-cluster2 zookeeper"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

kafka_client () {
    "${DOCKER_COMPOSE[@]}" run --rm kafka-client "$@"
}

run_log "Produce message to topic 'apples' (routes to cluster1)"
kafka_client /bin/bash -c "echo 'hello from apples' | kafka-console-producer --request-required-acks 1 --producer-property enable.idempotence=false --broker-list proxy:10000 --topic apples"

run_log "Produce message to topic 'bananas' (routes to cluster2)"
kafka_client /bin/bash -c "echo 'hello from bananas' | kafka-console-producer --request-required-acks 1 --producer-property enable.idempotence=false --broker-list proxy:10000 --topic bananas"

run_log "Verify message landed in cluster1 (consume directly from cluster1)"
kafka_client kafka-console-consumer --bootstrap-server kafka-cluster1:9092 --topic apples --from-beginning --max-messages 1 | grep "hello from apples"

run_log "Verify message landed in cluster2 (consume directly from cluster2)"
kafka_client kafka-console-consumer --bootstrap-server kafka-cluster2:9092 --topic bananas --from-beginning --max-messages 1 | grep "hello from bananas"

run_log "Consume 'apples' through mesh filter"
kafka_client kafka-console-consumer --bootstrap-server proxy:10000 --topic apples --partition 0 --from-beginning --max-messages 1 | grep "hello from apples"

run_log "Consume 'bananas' through mesh filter"
kafka_client kafka-console-consumer --bootstrap-server proxy:10000 --topic bananas --partition 0 --from-beginning --max-messages 1 | grep "hello from bananas"

run_log "Check Envoy stats for produce and fetch requests"
stats_output=$(_curl "http://localhost:${PORT_ADMIN}/stats?filter=kafka")
echo "$stats_output" | grep "produce_request" | grep -v ": 0"
echo "$stats_output" | grep "fetch_request" | grep -v ": 0"
echo "$stats_output" | grep "metadata_request" | grep -v ": 0"

run_log "Test high-volume producing with batched records"
# Send 20 messages rapidly to trigger producer batching
kafka_client /bin/bash -c " \
    for i in {1..20}; do \
        echo \"apricot message \$i\"; \
    done | kafka-console-producer --request-required-acks 1 --producer-property enable.idempotence=false --broker-list proxy:10000 --topic apricots"

run_log "Verify all 20 messages arrived at cluster1"
# Consume all messages and count them
message_count=$(kafka_client kafka-console-consumer --bootstrap-server kafka-cluster1:9092 --topic apricots --from-beginning --max-messages 20 2>/dev/null | wc -l)
message_count=${message_count:-0}
run_log "Received $message_count messages from apricots topic"

if [[ "$message_count" -eq 20 ]]; then
    run_log "SUCCESS: All 20 messages arrived at cluster1"
else
    echo "ERROR: Expected 20 messages but received $message_count" >&2
    exit 1
fi

run_log "Verify produce metrics reflect the batched requests"
# Get the produce_request count - it should be greater than 0 and likely less than 20 (due to batching)
stats_output=$(_curl "http://localhost:${PORT_ADMIN}/stats?filter=kafka.kafka_mesh.request.produce_request")
produce_count=$(echo "$stats_output" | grep "produce_request:" | cut -f2 -d':' | tr -d ' ')
produce_count=${produce_count:-0}
run_log "Total produce_request count: $produce_count"

if [[ "$produce_count" -gt 0 ]]; then
    run_log "SUCCESS: Produce requests tracked correctly (count: $produce_count)"
else
    echo "ERROR: No produce requests tracked" >&2
    exit 1
fi
