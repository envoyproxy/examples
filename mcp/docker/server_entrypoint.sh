#!/bin/sh
#
# The mcp-server service's entrypoint, in docker-compose.yaml. Clears the shared run directory of an
# earlier run, and starts mcp_server.py on all of the container's interfaces, so that the envoy
# service can reach it as mcp-server. See README.md.

set -eu

# Envoy starts only once this server is healthy, so it opens its access log after this. Envoy runs
# as a non-root user: let it write into the run directory, as into /tmp.
mkdir -p "${E2E_RUN_DIR}"
chmod 1777 "${E2E_RUN_DIR}"
rm -f "${E2E_RUN_DIR}/access.log" "${E2E_RUN_DIR}/backend_requests.jsonl" \
  "${E2E_RUN_DIR}/stats.txt" "${E2E_RUN_DIR}/server_info.json" "${E2E_RUN_DIR}/client_output.txt"

exec python -u mcp_server.py --host 0.0.0.0 --port "${MCP_SERVER_PORT}" \
  --request-log "${E2E_RUN_DIR}/backend_requests.jsonl"
