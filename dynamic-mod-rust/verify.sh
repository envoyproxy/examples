#!/bin/bash -e

export NAME=dynamic-mod-rust
export PORT_PROXY="${DYNAMIC_MOD_RUST_PORT_PROXY:-10510}"

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"

run_log "Test connection"
wait_for 10 bash -c "\
         responds_with \
         'Request served by' \
         http://localhost:${PORT_PROXY}"

run_log "Test dynamic module response header"
responds_with_header \
    "x-dynamic-module: FOO" \
    "http://localhost:${PORT_PROXY}"

run_log "Test dynamic module response body suffix"
responds_with \
    "Hello from the Rust dynamic module" \
    "http://localhost:${PORT_PROXY}"

run_log "Bring down the proxy"
"${DOCKER_COMPOSE[@]}" stop proxy

run_log "Update the filter config in envoy.yaml"
sed -i'.bak' s/response_header_value:\ FOO/response_header_value:\ BAR/ envoy.yaml

run_log "Bring the proxy back up"
"${DOCKER_COMPOSE[@]}" build proxy

# Restore the original config - the updated config is already baked into the
# rebuilt image.
mv envoy.yaml.bak envoy.yaml

"${DOCKER_COMPOSE[@]}" up -d --force-recreate proxy
wait_for 20 bash -c "\
         responds_with_header \
         'x-dynamic-module: BAR' \
         http://localhost:${PORT_PROXY}"

run_log "Test updated dynamic module response header"
responds_with_header \
    "x-dynamic-module: BAR" \
    "http://localhost:${PORT_PROXY}"

run_log "Test dynamic module response body suffix"
responds_with \
    "Hello from the Rust dynamic module" \
    "http://localhost:${PORT_PROXY}"
