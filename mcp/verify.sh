#!/bin/bash -e

export NAME=mcp
export PATHS=.,rest_backend

# shellcheck source=verify-common.sh
. "$(dirname "${BASH_SOURCE[0]}")/../verify-common.sh"


run_log "MCP backend: run the regression cases"
"${DOCKER_COMPOSE[@]}" exec -T mcp-client python -u docker/client_entrypoint.py

# Known gaps' checks that fail, or now pass (FIXED), are reported without failing the run.
run_log "REST backend: run the MCP JSON-REST bridge cases"
"${DOCKER_COMPOSE[@]}" -f rest_backend/docker-compose.yaml exec -T rest-client \
    python -u docker/client_entrypoint.py
