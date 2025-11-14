#!/bin/bash -e

export NAME=reverse_tunnel
# Port on upstream envoy which accepts requests to be sent to downstream
# services through reverse tunnels.
export PORT_PROXY="${REVERSE_TUNNEL_PORT_PROXY:-8085}"
# Admin port on downstream envoy.
export PORT_ADMIN_DOWNSTREAM="${REVERSE_TUNNEL_ADMIN_DOWNSTREAM:-8888}"
# Admin port on upstream envoy.
export PORT_ADMIN_UPSTREAM="${REVERSE_TUNNEL_ADMIN_UPSTREAM:-8889}"
# Reverse connection API port on downstream envoy.
export PORT_REVERSE_API_DOWNSTREAM="${REVERSE_TUNNEL_REVERSE_API_DOWNSTREAM:-9000}"
# Reverse connection API port on upstream envoy.
export PORT_REVERSE_API_UPSTREAM="${REVERSE_TUNNEL_REVERSE_API_UPSTREAM:-9001}"


# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

# Wait for reverse tunnel establishment - check downstream stats first
run_log "Wait for reverse tunnel establishment"
wait_for 60 bash -c "responds_with 'downstream_reverse_connection.cluster.upstream-cluster.connected: 1' 'http://localhost:${PORT_ADMIN_DOWNSTREAM}/stats?hidden=include'"

# Verify downstream stats.
run_log "Verify reverse tunnel establishment - downstream stats"
responds_with \
    "downstream_reverse_connection.cluster.upstream-cluster.connected: 1" \
    "http://localhost:${PORT_ADMIN_DOWNSTREAM}/stats?hidden=include"

run_log "Verify no pending downstream connections"
responds_with \
    "downstream_reverse_connection.cluster.upstream-cluster.connecting: 0" \
    "http://localhost:${PORT_ADMIN_DOWNSTREAM}/stats?hidden=include"

# Verify upstream stats.
run_log "Verify reverse tunnel establishment - upstream stats"
responds_with \
    "upstream_reverse_connection.clusters.downstream-cluster: 1" \
    "http://localhost:${PORT_ADMIN_UPSTREAM}/stats?hidden=include"

run_log "Verify upstream received connections from downstream node"
responds_with \
    "upstream_reverse_connection.nodes.downstream-node: 1" \
    "http://localhost:${PORT_ADMIN_UPSTREAM}/stats?hidden=include"

# Verify data requests through reverse tunnel.
run_log "Test reverse tunnel with cluster ID routing"
responds_with \
    "URI: /downstream_service" \
    "http://localhost:${PORT_PROXY}/downstream_service" \
    -H "x-cluster-id: downstream-cluster"

run_log "Test reverse tunnel with node ID routing"
responds_with \
    "URI: /downstream_service" \
    "http://localhost:${PORT_PROXY}/downstream_service" \
    -H "x-node-id: downstream-node"
